import asyncio
import logging
from enum import Enum
from PyQt6.QtCore import QThread, pyqtSlot
from core_bridge import VascoSignals
from brain_router import BrainRouter
from executor import ScriptExecutor
from ocr_module import OCRModule
from memory_manager import MemoryManager
from observer_module import ObserverModule

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
    SUGGESTION = "SUGGESTION"

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
        self.observer = ObserverModule(self.ocr)
        self.tts = tts
        self.loop = None
        self.asr = None # Reference to the ASR recognizer
        self.observer_enabled = True # Default to enabled

    def set_state(self, state: VascoState):
        """Updates the core state and notifies the UI."""
        logger.info(f"State transition: {self.state.value} -> {state.value}")
        self.state = state
        # Emit signal to the UI thread
        self.signals.state_changed.emit(state.value)

    def set_asr(self, recognizer):
        """Links the ASR recognizer to the core."""
        self.asr = recognizer
        logger.info("ASR recognizer linked to VascoCore.")

    def _calibration_callback(self, index, text):
        """Callback used by ASR module to update UI during calibration."""
        # Update Dynamic Island text
        self.signals.text_update.emit(text)

    async def ensure_calibration(self):
        """Checks if wake word calibration is needed and runs it if so."""
        if not self.asr:
            logger.warning("ASR not yet linked. Skipping calibration check.")
            return

        # Check if we are using the default wake word (meaning no calibration has happened)
        from asr_module import DEFAULT_WAKE_WORD
        if self.asr.wake_word == DEFAULT_WAKE_WORD.lower():
            logger.info("No calibrated wake word found. Starting first-run calibration...")

            # 1. Notify User
            self.set_state(VascoState.LISTENING)
            if self.tts:
                self.tts.speak("Hello! I'm Vasco. To make sure I recognize you, let's calibrate your wake word. Please say 'Hey Vasco' when you're ready.")
                while self.tts.is_currently_speaking():
                    await asyncio.sleep(0.1)

            # 2. Run Calibration in executor (blocking call)
            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(
                None,
                lambda: self.asr.calibrate(progress_callback=self._calibration_callback)
            )

            if success:
                logger.info("Calibration successful.")
                if self.tts:
                    self.tts.speak("Perfect. I've learned your voice. You can now wake me up by saying Hey Vasco.")
                    while self.tts.is_currently_speaking():
                        await asyncio.sleep(0.1)
            else:
                logger.error("Calibration failed.")
                if self.tts:
                    self.tts.speak("I had some trouble hearing you. We'll try again next time.")
                    while self.tts.is_currently_speaking():
                        await asyncio.sleep(0.1)

            self.set_state(VascoState.IDLE)
        else:
            logger.info(f"Using calibrated wake word: {self.asr.wake_word}")

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

        text_lower = text.lower()

        # Privacy Controls: Toggle Background Observer
        if "disable observer" in text_lower or "stop watching" in text_lower:
            self.observer_enabled = False
            self.set_state(VascoState.SPEAKING)
            if self.tts:
                self.tts.speak("Background observation disabled. I'll stop monitoring your screen.")
                while self.tts.is_currently_speaking():
                    await asyncio.sleep(0.1)
            await asyncio.sleep(1)
            self.set_state(VascoState.IDLE)
            return "observer_disabled"

        if "enable observer" in text_lower or "start watching" in text_lower:
            self.observer_enabled = True
            self.set_state(VascoState.SPEAKING)
            if self.tts:
                self.tts.speak("Background observation enabled. I'm now monitoring for errors on your screen.")
                while self.tts.is_currently_speaking():
                    await asyncio.sleep(0.1)
            await asyncio.sleep(1)
            self.set_state(VascoState.IDLE)
            return "observer_enabled"

        # 1. Handle Explicit Memory Requests
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

            # 1. Ensure wake word is calibrated
            await self.ensure_calibration()

            # Start the background observation loop
            asyncio.create_task(self._observation_loop())

            # Wait until stop event is set
            await self._stop_event.wait()
        except asyncio.CancelledError:
            logger.info("VascoCore async loop cancelled.")
        finally:
            logger.info("VascoCore async loop stopped.")

    async def _observation_loop(self):
        """
        Background task that monitors the environment and triggers proactive suggestions.
        """
        logger.info("Starting Background Observer loop...")
        # Expanded set of proactive keywords to monitor
        PROACTIVE_KEYWORDS = ["error", "crash", "failed", "exception", "timeout", "critical", "denied"]

        while not self._stop_event.is_set():
            try:
                if not self.observer_enabled:
                    await asyncio.sleep(5)
                    continue

                # Get current context
                loop = asyncio.get_running_loop()
                ctx = await loop.run_in_executor(None, self.observer.get_current_context)


                # Proactive Trigger: Check window title AND screen content
                combined_content = f"{ctx['window_title']} {ctx['screen_text']}".lower()
                if any(word in combined_content for word in PROACTIVE_KEYWORDS):
                    if self.state == VascoState.IDLE:
                        logger.info(f"Proactive trigger: Failure marker detected! Context: {combined_content[:100]}...")
                        self.set_state(VascoState.SUGGESTION)
                        if self.tts:
                            self.tts.speak("I noticed something went wrong on your screen. Would you like me to help you troubleshoot this?")
                            while self.tts.is_currently_speaking():
                                await asyncio.sleep(0.1)

                        # Return to IDLE after a while if no interaction
                        await asyncio.sleep(10)
                        if self.state == VascoState.SUGGESTION:
                            self.set_state(VascoState.IDLE)

                await asyncio.sleep(5) # Check every 5 seconds
            except Exception as e:
                logger.error(f"Observation loop error: {e}")
                await asyncio.sleep(10)


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


