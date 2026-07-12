import sys
from PyQt6.QtWidgets import QApplication, QWidget, QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QPropertyAnimation, QRect, QEasingCurve, QPoint, QSize
from PyQt6.QtGui import QColor, QPalette

class DynamicIsland(QWidget):
    def __init__(self):
        super().__init__()

        # Window setup: Frameless, Always-on-top, Translucent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # State Configuration
        # format: (width, height, color, text)
        self.states = {
            "IDLE": (150, 35, "#2c3e50", "Jarvis"),
            "LISTENING": (300, 50, "#3498db", "Listening..."),
            "THINKING": (300, 50, "#9b59b6", "Thinking..."),
            "SPEAKING": (300, 50, "#2ecc71", "Speaking..."),
            "EXECUTING": (300, 50, "#e67e22", "Executing..."),
        }
        self.current_state = "IDLE"

        # UI Components
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setObjectName("islandContainer")
        self.container.setStyleSheet(self._get_style("#2c3e50"))

        self.label = QLabel("Jarvis", self.container)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: white; font-family: 'Segoe UI', sans-serif; font-weight: bold; font-size: 14px;")

        # Center the label in the container
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.label)

        self.main_layout.addWidget(self.container)

        # Sizing and Positioning
        self.setFixedSize(*self.states["IDLE"][:2])
        self._position_on_screen()

        # Animation setup
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def _get_style(self, color):
        return f"""
            #islandContainer {{
                background-color: {color};
                border-radius: {self.height() // 2}px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
        """

    def _position_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = screen.y() + 10 # Slight offset from the very top
        self.move(x, y)

    def set_state(self, state):
        if state not in self.states:
            print(f"Invalid state: {state}")
            return

        self.current_state = state
        width, height, color, text = self.states[state]

        # Update text and style
        self.label.setText(text)
        self.container.setStyleSheet(self._get_style(color))

        # Animate size and position
        screen = QApplication.primaryScreen().availableGeometry()
        new_x = (screen.width() - width) // 2
        new_y = screen.y() + 10

        self.animation.stop()
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(QRect(new_x, new_y, width, height))
        self.animation.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)

    island = DynamicIsland()
    island.show()

    # --- TEST LOOP ---
    from PyQt6.QtCore import QTimer

    test_states = ["IDLE", "LISTENING", "THINKING", "SPEAKING", "EXECUTING", "IDLE"]
    state_index = 0

    def cycle_state():
        global state_index
        state = test_states[state_index]
        island.set_state(state)
        state_index = (state_index + 1) % len(test_states)

    timer = QTimer()
    timer.timeout.connect(cycle_state)
    timer.start(2000) # Change state every 2 seconds

    sys.exit(app.exec())
