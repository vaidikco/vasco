import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from core_bridge import VascoSignals
from ui_shell import DynamicIsland

def test_signal_bridge():
    app = QApplication(sys.argv)

    # 1. Setup Signal Bridge and UI
    signals = VascoSignals()
    island = DynamicIsland(signals=signals)
    island.show()

    # 2. Define a sequence of updates to verify visually
    # (state, text)
    test_sequence = [
        ("IDLE", "Vasco Ready"),
        ("LISTENING", "I'm listening..."),
        ("THINKING", "Processing your request..."),
        ("SPEAKING", "Here is the answer..."),
        ("EXECUTING", "Running command..."),
        ("IDLE", "Back to sleep"),
    ]

    state_idx = 0

    def run_test():
        nonlocal state_idx
        if state_idx >= len(test_sequence):
            print("Test sequence complete. Closing in 2 seconds...")
            QTimer.singleShot(2000, app.quit)
            return

        state, text = test_sequence[state_idx]
        print(f"Emitting: state={state}, text={text}")

        # Emit signals
        signals.state_changed.emit(state)
        signals.text_update.emit(text)

        state_idx += 1

    # Update every 2 seconds
    timer = QTimer()
    timer.timeout.connect(run_test)
    timer.start(2000)

    print("Starting signal bridge verification...")
    print("Observe the Dynamic Island for state and text changes.")
    sys.exit(app.exec())

if __name__ == "__main__":
    test_signal_bridge()


