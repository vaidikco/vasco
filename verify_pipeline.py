import sys
import time
import threading
from PyQt6.QtWidgets import QApplication
from core_bridge import VascoSignals
from Vasco_core import CoreWorker
from tts_module import TextToSpeech
from asr_module import SpeechRecognizer
from ui_shell import DynamicIsland

def simulate_asr(core):
    time.sleep(2) # Wait for loop to initialize
    print("\n[Sim] Simulating Wake Word: 'Hey Vasco'...")
    core.handle_asr_result("hey Vasco")
    time.sleep(2)

    print("\n[Sim] Simulating Command: 'Open Notepad'...")
    core.handle_asr_result("open notepad")
    time.sleep(5)

    print("\n[Sim] Simulating Wake Word: 'Hey Vasco'...")
    core.handle_asr_result("hey Vasco")
    time.sleep(2)

    print("\n[Sim] Simulating Cloud Query: 'What is the weather?'...")
    core.handle_asr_result("what is the weather?")
    time.sleep(10)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    signals = VascoSignals()
    tts = TextToSpeech()

    island = DynamicIsland(signals=signals)
    island.show()

    worker = CoreWorker(signals=signals, tts=tts)
    worker.start()

    # Start simulation thread
    sim_thread = threading.Thread(target=simulate_asr, args=(worker.core,), daemon=True)
    sim_thread.start()

    print("Pipeline verification started. Watch the UI (Dynamic Island) for state transitions.")
    print("Expected sequence:")
    print("1. IDLE -> LISTENING (on 'hey Vasco')")
    print("2. LISTENING -> THINKING -> EXECUTING -> IDLE (on 'open notepad')")
    print("3. LISTENING -> THINKING -> SPEAKING -> IDLE (on 'what is the weather?')")

    # Run for a while then exit
    time.sleep(20)
    worker.stop()
    print("Verification complete.")
    sys.exit(0)

