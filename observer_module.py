import pygetwindow as gw
import logging
import time
from typing import Dict, Any, Optional
from ocr_module import OCRModule

logger = logging.getLogger("ObserverModule")

class ObserverModule:
    """
    The Background Observer allows Vasco to 'sense' the environment.
    It tracks the active window and can perform light OCR to understand the context.
    """
    def __init__(self, ocr_module: OCRModule):
        self.ocr = ocr_module
        self.last_window = None

    def get_current_context(self) -> Dict[str, Any]:
        """
        Captures the current environment context.
        Returns: { 'window_title': str, 'screen_text': str, 'changed': bool }
        """
        try:
            # Get the active window
            active_window = gw.getActiveWindow()
            window_title = active_window.title if active_window else "Unknown"

            # Check if the window has changed
            changed = (window_title != self.last_window)
            self.last_window = window_title

            # Perform a light OCR scan for context
            # We only do a full scan if the window changed or periodically
            success, screen_text = self.ocr.scan_screen()

            return {
                "window_title": window_title,
                "screen_text": screen_text if success else "",
                "changed": changed
            }
        except Exception as e:
            logger.error(f"Observer failed to capture context: {e}")
            return {"window_title": "Error", "screen_text": "", "changed": False}

if __name__ == "__main__":
    # Simple self-test
    import logging
    logging.basicConfig(level=logging.INFO)

    from ocr_module import OCRModule
    ocr = OCRModule()
    observer = ObserverModule(ocr)

    print("Observing environment... (Press Ctrl+C to stop)")
    try:
        while True:
            ctx = observer.get_current_context()
            print(f"Window: {ctx['window_title']} | Changed: {ctx['changed']}")
            time.sleep(2)
    except KeyboardInterrupt:
        print("Stopped observing.")
