import sys
import ctypes
from ctypes import wintypes
from PyQt6.QtWidgets import QApplication, QWidget, QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QPropertyAnimation, QRect, QEasingCurve, QPoint, QSize
from PyQt6.QtGui import QColor, QPalette

# Win32 API for Acrylic Blur
class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_int),
        ("AnimationId", ctypes.c_int),
    ]

class WINDOWCOMPOSITIONCORE(ctypes.Structure):
    _fields_ = [
        ("SizingMode", ctypes.c_int),
        ("AccentPolicy", ACCENT_POLICY),
    ]

def SetWindowCompositionAttribute(hwnd, data):
    return ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))

class DynamicIsland(QWidget):
    def __init__(self):
        super().__init__()

        # Window setup: Frameless, Always-on-top, Translucent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Enable native Windows Acrylic blur
        self.enable_blur_behind()

        # State Configuration
        # format: (width, height, color, text)
        # Using rgba for Acrylic transparency
        self.states = {
            "IDLE": (150, 35, "rgba(44, 62, 80, 0.4)", "Jarvis"),
            "LISTENING": (300, 50, "rgba(52, 152, 219, 0.4)", "Listening..."),
            "THINKING": (300, 50, "rgba(155, 89, 182, 0.4)", "Thinking..."),
            "SPEAKING": (300, 50, "rgba(46, 204, 113, 0.4)", "Speaking..."),
            "EXECUTING": (300, 50, "rgba(230, 126, 34, 0.4)", "Executing..."),
        }
        self.current_state = "IDLE"

        # UI Components
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setObjectName("islandContainer")
        self.container.setStyleSheet(self._get_style(self.states["IDLE"][2]))

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
        self.animation.setDuration(450)
        self.animation.setEasingCurve(QEasingCurve.Type.OutBack)

    def enable_blur_behind(self):
        """Applies the native Windows Acrylic blur effect to the current window."""
        hwnd = int(self.winId())

        # AccentState 4 = ACCENT_ENABLE_ACRYLICBLUR
        # GradientColor is ABGR. We use a subtle tint.
        policy = ACCENT_POLICY(
            AccentState=4,
            AccentFlags=2,
            GradientColor=0x00FFFFFF, # White tint, alpha 0
            AnimationId=0
        )

        core = WINDOWCOMPOSITIONCORE(
            SizingMode=0,
            AccentPolicy=policy
        )

        SetWindowCompositionAttribute(hwnd, core)

    def _get_style(self, color):
        return f"""
            #islandContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 rgba(255, 255, 255, 0.3),
                                            stop:1 {color});
                border: 1px solid rgba(255, 255, 255, 0.4);
                border-radius: {self.height() // 2}px;
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
