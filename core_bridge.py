from PyQt6.QtCore import QObject, pyqtSignal

class VascoSignals(QObject):
    """
    Signal bridge to synchronize state and text updates between
    the Core logic and the UI Shell.
    """
    state_changed = pyqtSignal(str)
    text_update = pyqtSignal(str)

