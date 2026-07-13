"""The Dynamic Island UI shell (PyQt6) and the Qt<->asyncio plumbing.

Fixes over the original ui_shell.py:
- The file actually parses now — a duplicated OCRWaveOverlay class containing
  literal "... [existing code] ..." placeholder text was removed.
- Win32 Acrylic blur is guarded behind sys.platform, so the UI runs on
  macOS/Linux too (plain translucency there).
- Broken `from Vasco_core import ...` import fixed; duplicated style/text
  update block removed.
- Clicking the island toggles listening — handy when you don't want to
  say the wake word (or don't have a mic).
"""

import asyncio
import logging
import math
import sys

from PyQt6.QtCore import (
    QEasingCurve, QObject, QPropertyAnimation, QRect, Qt, QThread, QTimer,
    QVariantAnimation, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from vasco.core import VascoCore

logger = logging.getLogger("UI")

IS_WINDOWS = sys.platform == "win32"


class VascoSignals(QObject):
    """Bridge between the core (worker thread) and the UI (main thread)."""

    state_changed = pyqtSignal(str)
    text_update = pyqtSignal(str)
    audio_level = pyqtSignal(float)  # live mic loudness 0..1 while listening


class CoreWorker(QThread):
    """Runs VascoCore's asyncio loop on a background thread."""

    def __init__(self, signals: VascoSignals, tts=None):
        super().__init__()
        self.signals = signals
        self.core = VascoCore(signals, tts=tts)
        self._loop = None

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.core.loop = self._loop
        logger.info("CoreWorker: starting asyncio loop.")
        try:
            self._loop.run_until_complete(self.core.run())
        except Exception:
            logger.exception("CoreWorker crashed")
        finally:
            self._loop.close()
            logger.info("CoreWorker: loop closed.")

    def stop(self):
        self.core.stop()
        self.quit()
        self.wait(3000)


def enable_windows_blur(widget: QWidget):
    """Native Acrylic blur — Windows only, silently skipped elsewhere."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        class ACCENT_POLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_int),
                ("AnimationId", ctypes.c_int),
            ]

        class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.POINTER(ACCENT_POLICY)),
                ("SizeOfData", ctypes.c_size_t),
            ]

        accent = ACCENT_POLICY(AccentState=4, AccentFlags=2,
                               GradientColor=0x00FFFFFF, AnimationId=0)
        data = WINDOWCOMPOSITIONATTRIBDATA(
            Attribute=19,  # WCA_ACCENT_POLICY
            Data=ctypes.pointer(accent),
            SizeOfData=ctypes.sizeof(accent),
        )
        ctypes.windll.user32.SetWindowCompositionAttribute(
            int(widget.winId()), ctypes.byref(data)
        )
    except Exception as e:
        logger.warning("Acrylic blur unavailable: %s", e)


class OCRWaveOverlay(QWidget):
    """Full-screen pulsing border shown while Vasco scans the screen."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(QApplication.primaryScreen().geometry())

        self.glow_intensity = 0.0
        self.animation = QVariantAnimation()
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(1500)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.valueChanged.connect(self._update_glow)

    def _update_glow(self, value):
        self.glow_intensity = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = 0.1 + (self.glow_intensity * 0.5)
        pen = QPen(QColor(0, 150, 255, int(255 * alpha)))
        pen.setWidth(int(10 + (self.glow_intensity * 20)))
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(5, 5, -5, -5), 20, 20)

    def start_wave(self):
        self.show()
        self.animation.start()

    def stop_wave(self):
        self.animation.stop()
        self.hide()


class IslandContainer(QFrame):
    """Island body that can render a pulsing progress ring while processing."""

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
        pen = QPen(QColor(255, 255, 255, 100))
        pen.setWidth(3)
        painter.setPen(pen)
        span_angle = int(self.progress * 360 * 16)
        painter.drawArc(self.rect().adjusted(2, 2, -2, -2), 90 * 16, -span_angle)


class ListeningWave(QWidget):
    """An animated voice bar shown while Vasco is listening.

    A soft highlight sweeps left→right then right→left across a row of bars
    (so it visibly "searches"), and the whole thing grows brighter/taller with
    the live microphone level — it lights up when you actually speak.
    """

    N_BARS = 11

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._phase = 0.0          # sweep position driver
        self._level = 0.0          # target loudness (0..1)
        self._display = 0.0        # smoothed loudness actually drawn
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps
        self._timer.timeout.connect(self._tick)

    def start(self):
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        self._timer.stop()
        self._level = self._display = 0.0
        self.update()

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, level))

    def _tick(self):
        # Ease the drawn level toward the latest measured level for smoothness.
        self._display += (self._level - self._display) * 0.35
        self._phase += 0.12
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        # Sweep centre bounces left↔right (triangle-ish via sine of a slow phase).
        sweep = (math.sin(self._phase * 0.6) + 1) / 2  # 0..1
        centre = sweep * (self.N_BARS - 1)

        gap = 5
        bar_w = max(2.0, (w - (self.N_BARS - 1) * gap) / self.N_BARS)
        min_h = h * 0.16
        loud = 0.35 + 0.65 * self._display  # overall growth with voice
        for i in range(self.N_BARS):
            # Bump that follows the sweeping centre + a little per-bar shimmer.
            dist = abs(i - centre)
            bump = math.exp(-(dist * dist) / 5.0)
            shimmer = 0.5 + 0.5 * math.sin(self._phase * 1.7 + i * 0.9)
            amp = (0.25 + 0.75 * bump) * (0.5 + 0.5 * shimmer) * loud
            bar_h = min_h + (h - min_h) * amp
            x = i * (bar_w + gap)
            y = (h - bar_h) / 2
            alpha = int(150 + 105 * bump * (0.4 + 0.6 * self._display))
            painter.setBrush(QColor(255, 255, 255, alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h),
                                    int(bar_w / 2), int(bar_w / 2))


class DynamicIsland(QWidget):
    """A global overlay with a compact idle pill and an expanded reply card."""

    def __init__(self, signals: VascoSignals | None = None, on_activate=None,
                 on_submit=None, on_toggle_continuous=None):
        super().__init__()
        self.on_activate = on_activate
        self.on_submit = on_submit
        self.on_toggle_continuous = on_toggle_continuous
        self.continuous_on = False
        self.reply_visible = False

        # Tool + stay-on-top keeps this outside the normal app window stack,
        # so it can appear above whichever application the user is using.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if signals:
            signals.state_changed.connect(self.set_state)
            signals.text_update.connect(self.update_text)
            signals.audio_level.connect(self._on_audio_level)

        enable_windows_blur(self)
        self.scale_factor = QApplication.primaryScreen().logicalDotsPerInchX() / 96.0
        s = self.scale_factor
        self.states = {
            "IDLE":      (int(166 * s), int(42 * s), "rgba(24, 35, 52, 0.74)", "Vasco"),
            "LISTENING": (int(440 * s), int(112 * s), "rgba(33, 119, 204, 0.78)", "Listening"),
            "THINKING":  (int(400 * s), int(74 * s), "rgba(116, 73, 181, 0.78)", "Thinking"),
            "SPEAKING":  (int(400 * s), int(74 * s), "rgba(30, 158, 102, 0.78)", "Vasco"),
            "EXECUTING": (int(400 * s), int(74 * s), "rgba(196, 105, 28, 0.80)", "Working"),
            "SCANNING":  (int(400 * s), int(74 * s), "rgba(0, 128, 212, 0.80)", "Reading your screen"),
        }
        self.current_state = "IDLE"
        self.overlay = OCRWaveOverlay()
        self.progress_anim = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.container = IslandContainer()
        self.container.setObjectName("islandContainer")
        self.main_layout.addWidget(self.container)

        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(int(18 * s), int(10 * s), int(18 * s), int(11 * s))
        self.container_layout.setSpacing(int(7 * s))

        self.label = QLabel("Vasco", self.container)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(
            "color: white; font-family: 'SF Pro Display', 'SF Pro Text', 'Segoe UI', sans-serif; "
            "font-weight: 700; font-size: 14px; background: transparent;"
        )
        self.container_layout.addWidget(self.label)

        # Animated voice bar shown while listening (reacts to your voice).
        self.wave = ListeningWave(self.container)
        self.wave.setFixedHeight(int(34 * s))
        self.wave.hide()
        self.container_layout.addWidget(self.wave)

        self.reply_scroll = QScrollArea(self.container)
        self.reply_scroll.setWidgetResizable(True)
        self.reply_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.reply_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.reply_scroll.setStyleSheet("background: transparent;")
        self.reply_text = QLabel()
        self.reply_text.setWordWrap(True)
        self.reply_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.reply_text.setStyleSheet(
            "color: rgba(255,255,255,0.96); font-family: 'SF Pro Text', 'Segoe UI', sans-serif; "
            "font-size: 14px; line-height: 1.35; background: transparent;"
        )
        self.reply_scroll.setWidget(self.reply_text)
        self.reply_scroll.hide()
        self.container_layout.addWidget(self.reply_scroll)

        self.input_row = QWidget(self.container)
        input_layout = QHBoxLayout(self.input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(int(8 * s))
        self.command_input = QLineEdit(self.input_row)
        self.command_input.setPlaceholderText("Type a command…")
        self.command_input.setClearButtonEnabled(True)
        self.command_input.returnPressed.connect(self._submit_typed_command)
        self.command_input.setStyleSheet(
            "QLineEdit { color: white; background: rgba(0,0,0,0.22); border: 1px solid rgba(255,255,255,0.24); "
            "border-radius: 13px; padding: 8px 11px; font-size: 13px; }"
            "QLineEdit::placeholder { color: rgba(255,255,255,0.65); }"
        )
        self.send_button = QPushButton("Send", self.input_row)
        self.send_button.clicked.connect(self._submit_typed_command)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setStyleSheet(
            "QPushButton { color: white; background: rgba(255,255,255,0.20); border: 1px solid rgba(255,255,255,0.28); "
            "border-radius: 13px; padding: 7px 12px; font-weight: 700; }"
            "QPushButton:hover { background: rgba(255,255,255,0.32); }"
        )
        input_layout.addWidget(self.command_input, 1)
        input_layout.addWidget(self.send_button)
        self.input_row.hide()
        self.container_layout.addWidget(self.input_row)

        # Conversation toggle: when on, Vasco keeps listening after each reply
        # so you can talk back-and-forth without repeating the wake word.
        self.toggle_btn = QPushButton("↻  Keep listening", self.container)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle_continuous)
        self._style_toggle()
        self.toggle_btn.hide()
        self.container_layout.addWidget(self.toggle_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        idle_w, idle_h, idle_color, _ = self.states["IDLE"]
        self.resize(idle_w, idle_h)
        self.container.setStyleSheet(self._get_style(idle_color, idle_h))
        self._position_on_screen()
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # After Vasco finishes answering, the reply card lingers briefly so it
        # can be read, then collapses back to the idle pill on its own. Without
        # this the card stayed open forever and Vasco looked stuck/asleep.
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._collapse_to_idle)

    def mousePressEvent(self, event):
        if self.on_activate:
            self.on_activate()
        super().mousePressEvent(event)

    def _submit_typed_command(self):
        text = self.command_input.text().strip()
        if not text:
            return
        self.command_input.clear()
        if self.on_submit:
            self.on_submit(text)

    def _style_toggle(self):
        on = self.continuous_on
        bg = "rgba(46, 204, 113, 0.85)" if on else "rgba(255, 255, 255, 0.16)"
        border = "rgba(46, 204, 113, 0.95)" if on else "rgba(255, 255, 255, 0.30)"
        self.toggle_btn.setText("↻  Conversation on" if on else "↻  Keep listening")
        self.toggle_btn.setStyleSheet(
            f"QPushButton {{ color: white; background: {bg}; border: 1px solid {border}; "
            f"border-radius: 12px; padding: 5px 13px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ border: 1px solid rgba(255,255,255,0.55); }}"
        )

    def _toggle_continuous(self):
        self.continuous_on = self.toggle_btn.isChecked()
        self._style_toggle()
        if self.on_toggle_continuous:
            self.on_toggle_continuous(self.continuous_on)

    def _on_audio_level(self, level: float):
        self.wave.set_level(level)

    def _get_style(self, color, target_height: int):
        radius = min(int(26 * self.scale_factor), target_height // 2)
        return f"""
            #islandContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 rgba(255, 255, 255, 0.28),
                                            stop:1 {color});
                border: 1px solid rgba(255, 255, 255, 0.38);
                border-radius: {radius}px;
            }}
        """

    def _position_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.x() + (screen.width() - self.width()) // 2, screen.y() + 14)

    def _bring_forward(self):
        # Raise to the top visually, but do NOT activateWindow(): stealing
        # keyboard focus from the app the user is in on every state change is
        # disruptive (and interferes with whatever they're typing elsewhere).
        self.show()
        self.raise_()

    def _animate_to(self, width: int, height: int, color: str):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - width) // 2
        y = screen.y() + 14
        self.container.setStyleSheet(self._get_style(color, height))
        self.animation.stop()
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(QRect(x, y, width, height))
        self.animation.start()

    def _start_progress_animation(self):
        if self.progress_anim:
            return
        self.progress_anim = QVariantAnimation()
        self.progress_anim.setStartValue(0.0)
        self.progress_anim.setEndValue(1.0)
        self.progress_anim.setDuration(1800)
        self.progress_anim.setLoopCount(-1)
        self.progress_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.progress_anim.valueChanged.connect(self.container.set_progress)
        self.container.set_processing(True)
        self.progress_anim.start()

    def _stop_progress_animation(self):
        if self.progress_anim:
            self.progress_anim.stop()
            self.progress_anim = None
        self.container.set_processing(False)
        self.container.set_progress(0.0)

    def _hide_reply(self):
        self._collapse_timer.stop()
        self.reply_visible = False
        self.reply_scroll.hide()
        self.reply_text.clear()

    def _collapse_to_idle(self):
        """Timer callback: shrink the lingering reply card back to the pill."""
        if not self.reply_visible:
            return
        self._hide_reply()
        self.toggle_btn.hide()
        self.wave.stop()
        self.wave.hide()
        self.current_state = "IDLE"
        w, h, color, label = self.states["IDLE"]
        self.label.setText(label)
        self._animate_to(w, h, color)

    def update_text(self, text):
        """Show the entire reply and grow the overlay to its readable size."""
        self.reply_visible = True
        self.label.setText("Vasco")
        self.reply_text.setText(text)
        self.reply_scroll.show()
        self.input_row.hide()
        self.wave.stop()
        self.wave.hide()
        # Keep the conversation toggle visible on the reply card, so you can
        # turn "keep listening" on/off right after Vasco answers.
        self.toggle_btn.show()
        self._stop_progress_animation()

        screen = QApplication.primaryScreen().availableGeometry()
        width = min(int(620 * self.scale_factor), int(screen.width() * 0.72))
        width = max(int(390 * self.scale_factor), width)
        text_width = width - int(42 * self.scale_factor)
        metrics = QFontMetrics(self.reply_text.font())
        text_height = metrics.boundingRect(
            QRect(0, 0, text_width, 10_000),
            Qt.TextFlag.TextWordWrap, text,
        ).height() + int(8 * self.scale_factor)
        # Grow enough for ordinary multi-paragraph replies. Very long replies
        # remain fully accessible in the scrollable body instead of running off-screen.
        max_body = int(screen.height() * 0.62)
        body_height = min(max(text_height, int(36 * self.scale_factor)), max_body)
        self.reply_scroll.setFixedHeight(body_height)
        total_height = body_height + int(54 * self.scale_factor)
        self.current_state = "REPLY"
        # Longer replies linger longer before auto-collapsing, so there's time
        # to read them (bounded to a sensible range).
        self._reply_linger_ms = max(5000, min(22000, 3500 + len(text) * 55))
        self._animate_to(width, total_height, "rgba(30, 158, 102, 0.82)")
        self._bring_forward()

    def set_state(self, state):
        if state not in self.states:
            logger.warning("Invalid UI state: %s", state)
            return
        if state == "SCANNING":
            self.overlay.start_wave()
        else:
            self.overlay.stop_wave()

        # A completed answer lingers at idle so it can be read, then the timer
        # collapses it back to the pill on its own (so Vasco doesn't look stuck).
        if state == "IDLE" and self.reply_visible:
            self.current_state = "REPLY"
            self._collapse_timer.start(getattr(self, "_reply_linger_ms", 7000))
            return

        self.current_state = state
        width, height, color, label = self.states[state]
        if state != "IDLE":
            self._hide_reply()
        listening = state == "LISTENING"
        self.input_row.setVisible(listening)
        self.toggle_btn.setVisible(listening)
        if listening:
            self.wave.show()
            self.wave.start()
        else:
            self.wave.stop()
            self.wave.hide()

        if state in ("THINKING", "EXECUTING"):
            self._start_progress_animation()
        else:
            self._stop_progress_animation()

        self.label.setText(label)
        self._animate_to(width, height, color)
        if state != "IDLE":
            self._bring_forward()
        if listening:
            self.command_input.setFocus()
