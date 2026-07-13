from ocr_module import OCRModule
import logging

logging.basicConfig(level=logging.INFO)

def test_ocr():
    print("Testing OCR Module...")
    try:
        ocr = OCRModule()
        success, text = ocr.scan_screen()
        if success:
            print("\n[SUCCESS] OCR Scan Successful!")
            print(f"Extracted Text:\n{text}")
        else:
            print(f"\n[FAILURE] OCR Scan Failed: {text}")
    except Exception as e:
        print(f"\n[CRITICAL ERROR]: {e}")

if __name__ == "__main__":
    test_ocr()

