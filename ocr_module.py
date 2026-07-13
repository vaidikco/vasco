import mss
import easyocr
import numpy as np
import cv2
import logging
from typing import List, Tuple, Dict, Any

logger = logging.getLogger("OCRModule")

class OCRModule:
    """
    Handles screen capture and Optical Character Recognition (OCR) to
    allow Vasco to 'see' the contents of the user's screen.
    """
    def __init__(self, languages=['en']):
        logger.info("Initializing OCR Engine...")
        # Start with CPU to ensure stability during model download
        try:
            self.reader = easyocr.Reader(languages, gpu=False, verbose=False)
            logger.info("OCR Engine initialized on CPU.")
        except Exception as e:
            logger.error(f"Critical failure initializing OCR Engine: {e}")
            raise

    def scan_screen(self) -> Tuple[bool, str]:
        """
        Captures the primary screen and extracts all visible text.
        Returns: (success, extracted_text)
        """
        try:
            with mss.mss() as sct:
                # Capture the primary monitor
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)

                # Convert to numpy array for EasyOCR
                img = np.array(screenshot)

                # EasyOCR expects RGB, mss returns BGRA
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)

                # Perform OCR
                # detail=0 returns only the text list
                results = self.reader.readtext(img, detail=0)

                extracted_text = " ".join(results)

                if not extracted_text.strip():
                    return True, "No text detected on screen."

                return True, extracted_text

        except Exception as e:
            logger.error(f"OCR scan failed: {e}")
            return False, f"Error during screen scan: {str(e)}"

if __name__ == "__main__":
    # Simple self-test
    import logging
    logging.basicConfig(level=logging.INFO)

    ocr = OCRModule()
    success, text = ocr.scan_screen()
    if success:
        print("\n--- OCR Result ---\n")
        print(text)
        print("\n------------------")
    else:
        print(f"Failed: {text}")

