"""Screen reading (OCR) — optional feature.

Requires the optional dependencies: easyocr, opencv-python-headless, mss
(see requirements-optional.txt). Imports and the (large) model download
happen lazily on first use, so Vasco starts fast without them.
"""

import logging
from typing import Tuple

logger = logging.getLogger("OCRModule")


class OCRModule:
    """Captures the primary screen and extracts visible text."""

    def __init__(self, languages=("en",)):
        self.languages = list(languages)
        self._reader = None

    def _get_reader(self):
        if self._reader is None:
            import easyocr  # deferred: heavy import + first-run model download

            logger.info("Initializing OCR engine (first use)...")
            self._reader = easyocr.Reader(self.languages, gpu=False, verbose=False)
            logger.info("OCR engine ready.")
        return self._reader

    def scan_screen(self) -> Tuple[bool, str]:
        """Returns (success, extracted_text_or_error)."""
        try:
            import cv2
            import mss
            import numpy as np

            reader = self._get_reader()
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # primary monitor
                screenshot = sct.grab(monitor)
                img = np.array(screenshot)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)

            results = reader.readtext(img, detail=0)
            extracted = " ".join(results).strip()
            return True, extracted if extracted else "No text detected on screen."
        except ImportError as e:
            return False, f"missing optional dependency ({e.name})"
        except Exception as e:
            logger.error("OCR scan failed: %s", e)
            return False, f"Error during screen scan: {e}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ok, text = OCRModule().scan_screen()
    print(text if ok else f"Failed: {text}")
