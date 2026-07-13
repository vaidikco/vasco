import sys
from PyQt6.QtWidgets import QApplication, QWidget
import os

def test_window():
    print("Starting test window...")
    app = QApplication(sys.argv)
    w = QWidget()
    w.setWindowTitle("Vasco Test")
    w.resize(200, 200)
    w.show()
    print("Window shown. Closing in 2 seconds...")
    # Since we are in a non-interactive shell, we can't really keep it open
    # without an event loop, but we can check if it crashes.
    app.exec()

if __name__ == "__main__":
    test_window()
