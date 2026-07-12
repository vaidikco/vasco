import asyncio
import logging
from enum import Enum
from PyQt6.QtCore import QThread, pyqtSlot
from core_bridge import JarvisSignals
from brain_router import BrainRouter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JarvisCore")

class JarvisState(Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    EXECUTING = "EXECUTING"

class JarvisCore:
    """
    The central orchestrator for Jarvis. Manages the global state machine
    and coordinates between ASR, LLM, and TTS components.
    """
    def __init__(self, signals: JarvisSignals):
        self.signals = signals
        self.state = JarvisState.IDLE
        self._stop_event = asyncio.Event()
        self.router = BrainRouter()

    def set_state(self, state: JarvisState):
        """Updates the core state and notifies the UI."""
        logger.info(f"State transition: {self.state.value} -> {state.value}")
        self.state = state
        # Emit signal to the UI thread
        self.signals.state_changed.emit(state.value)

    async def process_text(self, text: str):
        """Processes user text through the brain router and manages state transitions."""
        logger.info(f"Processing text: {text}")

        # 1. Enter THINKING state
        self.set_state(JarvisState.THINKING)

        # 2. Route and get response
        route, prompt = await self.router.route_intent(text)
        logger.info(f"Router decided: {route}")

        # In a real system, we'd get the response here
        # response = await self.router.process(text)

        # 3. Determine next state
        if route == "local":
            # Local intents usually trigger execution
            self.set_state(JarvisState.EXECUTING)
            logger.info(f"Executing local command: {text}")
        else:
            # Cloud intents usually trigger a spoken response
            self.set_state(JarvisState.SPEAKING)
            logger.info(f"Speaking cloud response for: {text}")

        # Return to IDLE after a short delay (simulation)
        await asyncio.sleep(1)
        self.set_state(JarvisState.IDLE)

        return route

    async def run(self):
        """
        The main async entry point. This loop orchestrates the Jarvis pipeline.
        For now, it implements a test loop to verify UI responsiveness.
        """
        logger.info("JarvisCore async loop started.")
        try:
            while not self._stop_event.is_set():
                # Simulate the pipeline sequence
                # 1. IDLE
                self.set_state(JarvisState.IDLE)
                await asyncio.sleep(3)

                # 2. LISTENING
                self.set_state(JarvisState.LISTENING)
                await asyncio.sleep(2)

                # 3. THINKING
                self.set_state(JarvisState.THINKING)
                await asyncio.sleep(2)

                # 4. SPEAKING
                self.set_state(JarvisState.SPEAKING)
                await asyncio.sleep(2)

                # 5. EXECUTING
                self.set_state(JarvisState.EXECUTING)
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            logger.info("JarvisCore async loop cancelled.")
        finally:
            logger.info("JarvisCore async loop stopped.")

    def stop(self):
        """Signals the async loop to stop."""
        self._stop_event.set()

class CoreWorker(QThread):
    """
    A QThread wrapper that runs a dedicated asyncio event loop.
    This allows JarvisCore to run in the background without blocking the PyQt6 UI thread.
    """
    def __init__(self, signals: JarvisSignals):
        super().__init__()
        self.signals = signals
        self.core = JarvisCore(signals)
        self._loop = None

    def run(self):
        """Entry point for QThread. Sets up the asyncio loop and runs JarvisCore."""
        # Create a new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

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
