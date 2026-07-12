import sys
import ctypes
from ctypes import wintypes
from PyQt6.QtWidgets import QApplication, QWidget, QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QPropertyAnimation, QRect, QEasingCurve, QPoint, QSize, QVariantAnimation
from PyQt6.QtGui import QColor, QPalette, QPainter, QPen, QRadialGradient
from core_bridge import VascoSignals
from Vasco_core import CoreWorker
from asr_module import SpeechRecognizer
from tts_module import TextToSpeech
import threading

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

class OCRWaveOverlay(QWidget):
    """
    A full-screen, transparent overlay that displays a pulsing wave border
    when Vasco is scanning the screen.
    """
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Full screen
        self.screen_geom = QApplication.primaryScreen().geometry()
        self.setGeometry(self.screen_geom)

        # Animation for the wave effect
        self.glow_intensity = 0.0
        self.animation = QVariantAnimation()
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(1500)
        self.animation.setLoopCount(-1) # Infinite loop
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.valueChanged.connect(self.update_glow)

    def update_glow(self, value):
        self.glow_intensity = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Calculate pulse colors
        # Subtle white (0.1 alpha) -> Vibrant blue (0.6 alpha)
        alpha = 0.1 + (self.glow_intensity * 0.5)
        color = QColor(0, 150, 255, int(255 * alpha))

        pen = QPen(color)
        # Thickness pulses as well
        pen.setWidth(int(10 + (self.glow_intensity * 20)))
        painter.setPen(pen)

        # Draw the "wave" border
        rect = self.rect().adjusted(5, 5, -5, -5)
        painter.drawRoundedRect(rect, 20, 20)

    def start_wave(self):
        self.show()
        self.animation.start()

    def stop_wave(self):
        self.animation.stop()
        self.hide()

class OCRWaveOverlay(QWidget):
... [existing code] ...
    def stop_wave(self):
        self.animation.stop()
        self.hide()

class IslandContainer(QFrame):
    """
    A custom container for the Dynamic Island that can render a
    pulsing progress ring during processing states.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0.0
        self.is_processing = False

    def set_processing(self, active: bool):
        self.is_processing = active
        self.update()

    def set_progress(self, value: float):
        self.progress = value
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.is_processing:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw a subtle glowing ring around the edge
        pen = QPen(QColor(255, 255, 255, 100))
        pen.setWidth(3)
        painter.setPen(pen)

        rect = self.rect().adjusted(2, 2, -2, -2)
        # Draw only the progress arc
        span_angle = int(self.progress * 360 * 16)
        painter.drawArc(rect, 90 * 16, -span_angle)

class DynamicIsland(QWidget):
    def __init__(self, signals=None):
        super().__init__()

        # Window setup: Frameless, Always-on-top, Translucent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if signals:
            signals.state_changed.connect(self.set_state)
            signals.text_update.connect(self.update_text)

        # Enable native Windows Acrylic blur
        self.enable_blur_behind()

        # DPI Scaling
        self.scale_factor = QApplication.primaryScreen().logicalDotsPerInchX() / 96.0

        # State Configuration
        # format: (width, height, color, text)
        # Using rgba for Acrylic transparency
        self.states = {
            "IDLE": (int(150 * self.scale_factor), int(35 * self.scale_factor), "rgba(44, 62, 80, 0.4)", "Vasco"),
            "LISTENING": (int(300 * self.scale_factor), int(50 * self.scale_factor), "rgba(52, 152, 219, 0.4)", "Listening..."),
            "THINKING": (int(300 * self.scale_factor), int(50 * self.scale_factor), "rgba(155, 89, 182, 0.4)", "Thinking..."),
            "SPEAKING": (int(300 * self.scale_factor), int(50 * self.scale_factor), "rgba(46, 204, 113, 0.4)", "Speaking..."),
            "EXECUTING": (int(300 * self.scale_factor), int(50 * self.scale_factor), "rgba(230, 126, 34, 0.4)", "Executing..."),
            "SCANNING": (int(300 * self.scale_factor), int(50 * self.scale_factor), "rgba(0, 150, 255, 0.4)", "Scanning Screen..."),
        }
        self.current_state = "IDLE"

        # OCR Overlay
        self.overlay = OCRWaveOverlay()

        # UI Components
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = IslandContainer()
        self.container.setObjectName("islandContainer")


        # Sizing and Positioning - Must be set before style to get correct height() for border-radius
        self.setFixedSize(*self.states["IDLE"][:2])
        self.container.setStyleSheet(self._get_style(self.states["IDLE"][2]))

        self.label = QLabel("Vasco", self.container)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: white; font-family: 'Segoe UI', sans-serif; font-weight: bold; font-size: 14px;")

        # Center the label in the container
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.label)

        self.main_layout.addWidget(self.container)
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

        try:
            SetWindowCompositionAttribute(hwnd, core)
        except AttributeError:
            print("Warning: SetWindowCompositionAttribute not found. Blur effect disabled.")
            return

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

    def _start_progress_animation(self):
        """Animates the progress ring from 0 to 1."""
        self.progress_anim = QVariantAnimation()
        self.progress_anim.setStartValue(0.0)
        self.progress_anim.setEndValue(1.0)
        self.progress_anim.setDuration(2000)
        self.progress_anim.setLoopCount(-1)
        self.progress_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.progress_anim.valueChanged.connect(self.container.set_progress)
        self.progress_anim.start()

    def update_text(self, text):
        """Updates the label text without changing the overall state."""
        self.label.setText(text)

    def set_state(self, state):
        if state not in self.states:
            print(f"Invalid state: {state}")
            return

        # Handle OCR Overlay
        if state == "SCANNING":
            self.overlay.start_wave()
        else:
            self.overlay.stop_wave()

        self.current_state = state
        width, height, color, text = self.states[state]

        # Handle Progress Ring
        if state in ["THINKING", "EXECUTING"]:
            self.container.set_processing(True)
            self._start_progress_animation()
        else:
            self.container.set_processing(False)
            self.container.set_progress(0.0)

        # Update text and style
        self.label.setText(text)
        self.container.setStyleSheet(self._get_style(color))


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

    # Initialize signals
    signals = VascoSignals()

    # Initialize TTS
    tts = TextToSpeech()

    # Initialize UI
    island = DynamicIsland(signals=signals)
    island.show()

    # Initialize and start the Core Worker (Asyncio Orchestrator)
    worker = CoreWorker(signals=signals, tts=tts)
    worker.start()

    # Initialize ASR and start listening in a background thread
    recognizer = SpeechRecognizer(callback_function=worker.core.handle_asr_result)
    asr_thread = threading.Thread(target=recognizer.start_listening, daemon=True)
    asr_thread.start()

    sys.exit(app.exec())


