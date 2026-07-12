import asyncio
import logging
from enum import Enum
from PyQt6.QtCore import QThread, pyqtSlot
from core_bridge import VascoSignals
from brain_router import BrainRouter
from executor import ScriptExecutor
from ocr_module import OCRModule
from memory_manager import MemoryManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VascoCore")

class VascoState(Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    EXECUTING = "EXECUTING"
    SCANNING = "SCANNING"

class VascoCore:
    """
    The central orchestrator for Vasco. Manages the global state machine
    and coordinates between ASR, LLM, and TTS components.
    """
    def __init__(self, signals: VascoSignals, tts=None):
        self.signals = signals
        self.state = VascoState.IDLE
        self._stop_event = asyncio.Event()
        self.router = BrainRouter()
        self.executor = ScriptExecutor()
        self.ocr = OCRModule()
        self.memory = MemoryManager()
        self.tts = tts
        self.loop = None

    def set_state(self, state: VascoState):
        """Updates the core state and notifies the UI."""
        logger.info(f"State transition: {self.state.value} -> {state.value}")
        self.state = state
        # Emit signal to the UI thread
        self.signals.state_changed.emit(state.value)

    def handle_asr_result(self, text: str):
        """Callback for ASR module. Handles wake word and command capture."""
        logger.info(f"ASR Result: {text}")

        if self.loop is None:
            logger.warning("VascoCore loop not yet initialized. Dropping ASR result.")
            return

        asyncio.run_coroutine_threadsafe(self._process_asr_logic(text), self.loop)

    async def _process_asr_logic(self, text: str):
        """Internal async logic for ASR results."""
        from asr_module import WAKE_WORD

        if self.state == VascoState.IDLE:
            if WAKE_WORD in text:
                logger.info("Wake word detected!")
                self.set_state(VascoState.LISTENING)
        elif self.state == VascoState.LISTENING:
            # Any text received while LISTENING is treated as the command
            logger.info(f"Command captured: {text}")
            await self.process_text(text)

    async def process_text(self, text: str):
        """Processes user text through the brain router and manages state transitions."""
        logger.info(f"Processing text: {text}")

        # 1. Handle Explicit Memory Requests
        text_lower = text.lower()
        if "remember that" in text_lower:
            memory_content = text.split("remember that", 1)[1].strip()
            topic = f"Fact: {memory_content[:30]}..."
            self.memory.remember(topic, memory_content, category="user_facts")
            logger.info(f"Stored memory: {memory_content}")
            self.set_state(VascoState.SPEAKING)
            if self.tts:
                self.tts.speak("I've added that to my memory.")
                while self.tts.is_currently_speaking():
                    await asyncio.sleep(0.1)
            await asyncio.sleep(1)
            self.set_state(VascoState.IDLE)
            return "memory_saved"

        # 2. Check for OCR triggers
        if any(word in text_lower for word in ["look", "screen", "see", "what is on"]):
            logger.info("OCR trigger detected. Scanning screen...")
            self.set_state(VascoState.SCANNING)

            loop = asyncio.get_running_loop()
            success, screen_text = await loop.run_in_executor(None, self.ocr.scan_screen)

            if success:
                logger.info(f"Screen scan successful. Found: {screen_text[:100]}...")
                text = f"{text} [Screen Content: {screen_text}]"
            else:
                logger.error(f"Screen scan failed: {screen_text}")
                text = f"{text} (Screen scan failed)"

        # 3. Memory Retrieval (The Visual Brain)
        logger.info(f"Recalling memories for: {text}")
        memories = self.memory.recall(text)
        if memories:
            context_fragments = [m['content'] for m in memories]
            memory_context = "\n".join(context_fragments)
            text = f"{text} [Relevant Memories: {memory_context}]"
            logger.info(f"Injected {len(memories)} memories into context.")

        # 4. Enter THINKING state
        self.set_state(VascoState.THINKING)



        # 2. Route and get response
        route, prompt = await self.router.route_intent(text)
        logger.info(f"Router decided: {route}")

        # 3. Determine next state
        if route == "local":
            # Local intents trigger execution
            self.set_state(VascoState.EXECUTING)
            logger.info(f"Executing local command: {text}")

            # Generate script (mocked simulation of LLM)
            script = self._generate_local_script(text)
            if script:
                success, output = self.executor.execute_script(script)
                if success:
                    logger.info(f"Execution successful: {output}")
                else:
                    logger.error(f"Execution failed: {output}")
            else:
                logger.error(f"Could not generate script for: {text}")
        else:
            # Cloud intents usually trigger a spoken response
            self.set_state(VascoState.SPEAKING)
            logger.info(f"Speaking cloud response for: {text}")
            if self.tts:
                self.tts.speak(f"You said {text}. I am processing your request.")
                while self.tts.is_currently_speaking():
                    await asyncio.sleep(0.1)
            else:
                await asyncio.sleep(2)

        # Return to IDLE after a short delay
        await asyncio.sleep(1)
        self.set_state(VascoState.IDLE)

        return route

    def _generate_local_script(self, text: str) -> str:
        """
        Simulates an LLM generating a Python script for a local action.
        """
        text_lower = text.lower()
        if "open notepad" in text_lower:
            return "import os\nos.startfile('notepad.exe')"
        if "open calculator" in text_lower:
            return "import os\nos.startfile('calc.exe')"

        # Default fallback for other local commands
        return f"print('Simulated execution for: {text}')"

    async def run(self):
        """
        The main async entry point.
        """
        logger.info("VascoCore async loop started.")
        try:
            # Set initial state
            self.set_state(VascoState.IDLE)
            # Wait until stop event is set
            await self._stop_event.wait()
        except asyncio.CancelledError:
            logger.info("VascoCore async loop cancelled.")
        finally:
            logger.info("VascoCore async loop stopped.")

    def stop(self):
        """Signals the async loop to stop."""
        self._stop_event.set()

class CoreWorker(QThread):
    """
    A QThread wrapper that runs a dedicated asyncio event loop.
    This allows VascoCore to run in the background without blocking the PyQt6 UI thread.
    """
    def __init__(self, signals: VascoSignals, tts=None):
        super().__init__()
        self.signals = signals
        self.core = VascoCore(signals, tts=tts)
        self._loop = None

    def run(self):
        """Entry point for QThread. Sets up the asyncio loop and runs VascoCore."""
        # Create a new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.core.loop = self._loop

        logger.info("CoreWorker: Starting asyncio loop in separate thread.")
        try:
            self._loop.run_until_complete(self.core.run())
        except Exception as e:
            logger.exception(f"CoreWorker encountered an error: {e}")
        finally:
            self._loop.close()
            logger.info("CoreWorker: asyncio loop closed.")

    def stop(self):
        """Stops the core and the thread."""
        self.core.stop()
        self.quit()
        self.wait()


