import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from ui_shell import DynamicIsland

def run_debug():
    app = QApplication(sys.argv)
    island = DynamicIsland()
    island.show()
    print("Debug Island shown. Closing in 5 seconds...")
    # We use a timer to close it since we can't interact
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(5000, app.quit)
    sys.exit(app.exec())

if __name__ == "__main__":
    run_debug()
