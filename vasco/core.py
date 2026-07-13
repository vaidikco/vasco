"""VascoCore: the central state machine that ties ears, brain, and voice together.

Deliberately free of PyQt imports — the core runs headless (text REPL, tests)
and any UI attaches through a signals object with `.emit()`-style members.

Fixes over the original:
- Wake word actually triggers: the old code compared "hey Vasco" (capital V)
  against lowercased ASR text, so it could never match. Matching is now
  case-insensitive AND fuzzy, because Vosk hears "vasco" as "vasko"/"vas co".
- "hey vasco open safari" in one breath works (command extracted after wake).
- LISTENING times out back to IDLE instead of hanging forever.
- "Remember that ..." no longer crashes on capitalized input.
- Cloud replies are real LLM responses, spoken aloud, with tool use.
- ASR is paused while Vasco speaks so it doesn't hear itself.
- Blocking work (LLM, OCR, TTS, actions) runs off the event loop.
"""

import asyncio
import logging
import re
from difflib import SequenceMatcher
from enum import Enum
from typing import List, Optional, Tuple

from vasco.config import config
from vasco.memory import MemoryManager
from vasco.router import BrainRouter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("VascoCore")

OCR_TRIGGERS = (
    "on my screen", "on the screen", "read my screen", "read the screen",
    "look at my screen", "look at the screen", "what do you see",
    "what am i looking at",
)


class VascoState(Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    EXECUTING = "EXECUTING"
    SCANNING = "SCANNING"


class _NullSignal:
    def emit(self, *args, **kwargs):
        pass


class NullSignals:
    """Stand-in for the PyQt signal bridge when running headless."""

    def __init__(self):
        self.state_changed = _NullSignal()
        self.text_update = _NullSignal()


class WakeWordDetector:
    """Fuzzy wake-word matching tolerant of speech-recognition mangling."""

    # Real Vosk transcriptions observed for "hey Vasco" with the bundled
    # small English model.  Keep these narrowly scoped so ordinary speech
    # still does not wake the assistant.
    VOSK_WAKE_ALIASES = {"vago", "vasgo", "wasgo", "versego"}

    def __init__(self, wake_word: Optional[str] = None):
        self.wake_word = (wake_word or config.wake_word).lower().strip()
        self.name = self.wake_word.split()[-1]  # "vasco"

    def match(self, text: str) -> Tuple[bool, str]:
        """Returns (woke, command_after_wake_word)."""
        words = text.lower().split()
        # The name somewhere in the first few words wakes Vasco.
        for i, word in enumerate(words[:4]):
            if (SequenceMatcher(None, word, self.name).ratio() >= 0.78
                    or word in self.VOSK_WAKE_ALIASES):
                return True, " ".join(words[i + 1:]).strip()
        # Vosk sometimes splits the name across two tokens ("vas co").
        for i in range(min(3, max(0, len(words) - 1))):
            merged = words[i] + words[i + 1]
            if (SequenceMatcher(None, merged, self.name).ratio() >= 0.8
                    or merged in self.VOSK_WAKE_ALIASES):
                return True, " ".join(words[i + 2:]).strip()
        return False, ""


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


class VascoCore:
    """The orchestrator. Owns state, history, memory, and the brain router."""

    def __init__(self, signals=None, tts=None, asr=None,
                 router: Optional[BrainRouter] = None,
                 memory: Optional[MemoryManager] = None):
        self.signals = signals or NullSignals()
        self.tts = tts
        self.asr = asr  # needs .pause()/.resume() if provided
        self.state = VascoState.IDLE
        self.router = router or BrainRouter()
        self.memory = memory or MemoryManager()
        self.wake = WakeWordDetector()
        self.history: List[dict] = []
        # When True, Vasco keeps listening after each reply (conversation mode)
        # instead of returning to wake-word-only idle. Toggled from the UI.
        self.continuous_mode = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = asyncio.Event()
        self._listen_timeout_task: Optional[asyncio.Task] = None
        self._ocr = None
        self._ocr_failed = False

    # -- state ----------------------------------------------------------------

    def set_state(self, state: VascoState):
        if state != self.state:
            logger.info("State: %s -> %s", self.state.value, state.value)
        self.state = state
        # Tell the recognizer to use full-accuracy transcription while we're
        # actively capturing a command (post-wake).
        if self.asr is not None:
            self.asr.set_command_mode(state == VascoState.LISTENING)
        self.signals.state_changed.emit(state.value)

    # -- entry points from other threads ---------------------------------------

    def handle_asr_result(self, text: str):
        """Called from the ASR thread with each recognized utterance."""
        if self.loop is None:
            logger.warning("Core loop not ready; dropping ASR result.")
            return
        asyncio.run_coroutine_threadsafe(self._process_asr_logic(text), self.loop)

    def trigger_listening(self):
        """Called from the UI thread (island clicked) to toggle listening."""
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._toggle_listening)

    def submit_command(self, text: str):
        """Accept a typed command from the overlay without requiring a wake word."""
        if self.loop is None:
            logger.warning("Core loop not ready; dropping typed command.")
            return
        asyncio.run_coroutine_threadsafe(self.process_command(text), self.loop)

    def set_continuous(self, on: bool):
        """Toggle conversation mode (keep listening after each reply)."""
        self.continuous_mode = bool(on)
        logger.info("Conversation mode %s", "ON" if on else "OFF")

    def _toggle_listening(self):
        if self.state == VascoState.IDLE:
            self._enter_listening()
        elif self.state == VascoState.LISTENING:
            self._cancel_listen_timeout()
            self.set_state(VascoState.IDLE)

    # -- wake word / listening --------------------------------------------------

    async def _process_asr_logic(self, text: str):
        text = text.strip()
        if not text:
            return
        if self.state == VascoState.IDLE:
            woke, command = self.wake.match(text)
            if woke:
                logger.info("Wake word detected in: %r", text)
                if command:
                    await self.process_command(command)
                else:
                    self._enter_listening()
        elif self.state == VascoState.LISTENING:
            self._cancel_listen_timeout()
            await self.process_command(text)
        # In any other state Vasco is busy (possibly speaking) — ignore audio.

    def _enter_listening(self):
        self.set_state(VascoState.LISTENING)
        self._cancel_listen_timeout()
        self._listen_timeout_task = asyncio.get_running_loop().create_task(
            self._listen_timeout()
        )

    def _cancel_listen_timeout(self):
        if self._listen_timeout_task and not self._listen_timeout_task.done():
            self._listen_timeout_task.cancel()
        self._listen_timeout_task = None

    async def _listen_timeout(self):
        try:
            await asyncio.sleep(config.listen_timeout)
            if self.state == VascoState.LISTENING:
                logger.info("Listening timed out; returning to IDLE.")
                self.set_state(VascoState.IDLE)
        except asyncio.CancelledError:
            pass

    # -- command processing -----------------------------------------------------

    async def process_command(self, text: str) -> str:
        """Handle one user command end-to-end. Returns the spoken reply."""
        text = text.strip()
        if not text:
            self.set_state(VascoState.IDLE)
            return ""
        logger.info("Command: %s", text)
        loop = asyncio.get_running_loop()

        # 1. Explicit memory writes ("remember that I like my coffee black").
        m = re.search(r"\bremember(?: that)?\s+(.+)", text, re.IGNORECASE)
        if m:
            fact = m.group(1).strip()
            topic = f"Fact: {fact[:40]}"
            await loop.run_in_executor(
                None, lambda: self.memory.remember(topic, fact, "user_facts")
            )
            return await self._speak_and_idle("I've added that to my memory.")

        augmented = text

        # 2. Screen reading on request.
        lowered = text.lower()
        if any(trigger in lowered for trigger in OCR_TRIGGERS):
            self.set_state(VascoState.SCANNING)
            ok, screen_text = await loop.run_in_executor(None, self._scan_screen)
            if ok:
                augmented += f"\n[Screen Content: {_shorten(screen_text, 4000)}]"
            else:
                augmented += f"\n(Screen scan unavailable: {screen_text})"

        # 3. Recall relevant memories.
        memories = await loop.run_in_executor(None, lambda: self.memory.recall(text))
        if memories:
            context = "\n".join(_shorten(m["content"], 500) for m in memories)
            augmented += f"\n[Relevant Memories: {context}]"
            logger.info("Injected %d memories into context.", len(memories))

        # 4. Route to action / cloud / local brain.
        is_action = self.router.actions.match_text(text) is not None
        self.set_state(VascoState.EXECUTING if is_action else VascoState.THINKING)
        route, reply = await self.router.respond(augmented, list(self.history))
        logger.info("Route: %s | Reply: %s", route, _shorten(reply, 200))

        # No LLM available but the vault had something relevant? Answer from it.
        if route == "none" and memories:
            reply = "Here's what I remember: " + _shorten(memories[0]["content"], 300)

        # 5. Update conversation history (raw text, trimmed in pairs).
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": reply})
        keep = config.history_limit - (config.history_limit % 2)
        self.history = self.history[-keep:]

        return await self._speak_and_idle(reply)

    async def _speak_and_idle(self, reply: str) -> str:
        self.set_state(VascoState.SPEAKING)
        # The UI owns wrapping and resizing.  Sending the complete reply lets
        # the overlay grow to show it instead of cutting it off at 60 chars.
        self.signals.text_update.emit(reply)
        if self.tts:
            if self.asr:
                self.asr.pause()
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self.tts.speak_blocking, reply)
            finally:
                if self.asr:
                    self.asr.resume()
        # Conversation mode: keep listening for a follow-up instead of going
        # idle, so you can talk back-and-forth without repeating the wake word.
        if self.continuous_mode and self.asr is not None:
            self._enter_listening()
        else:
            self.set_state(VascoState.IDLE)
        return reply

    # -- OCR (optional dependency, lazy) ----------------------------------------

    def _scan_screen(self) -> Tuple[bool, str]:
        if self._ocr is None and not self._ocr_failed:
            try:
                from vasco.ocr import OCRModule
                self._ocr = OCRModule()
            except Exception as e:
                self._ocr_failed = True
                logger.warning("OCR unavailable: %s", e)
                return False, "OCR needs the easyocr and mss packages installed."
        if self._ocr is None:
            return False, "OCR needs the easyocr and mss packages installed."
        return self._ocr.scan_screen()

    # -- lifecycle ----------------------------------------------------------------

    async def run(self):
        self.loop = asyncio.get_running_loop()
        logger.info("VascoCore async loop started.")
        try:
            self.set_state(VascoState.IDLE)
            await self._stop_event.wait()
        except asyncio.CancelledError:
            logger.info("VascoCore async loop cancelled.")
        finally:
            logger.info("VascoCore async loop stopped.")

    def stop(self):
        if self.loop:
            self.loop.call_soon_threadsafe(self._stop_event.set)
        else:
            self._stop_event.set()
