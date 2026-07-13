import os
import sys
import json
import queue
import zipfile
import urllib.request
import sounddevice as sd
from difflib import SequenceMatcher
from vosk import Model, KaldiRecognizer


# Configuration
MODEL_URL_SMALL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_URL_BIG = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
MODEL_PATH = "model"
DEFAULT_WAKE_WORD = "hey vasco"
SETTINGS_FILE = "settings.json"

class SpeechRecognizer:
    def __init__(self, callback_function=None):
        self.callback = callback_function
        self.audio_queue = queue.Queue()
        self.model = self._load_model()
        self.recognizer = KaldiRecognizer(self.model, 16000)
        self.is_listening = False

        # Load calibrated wake word from settings or use default
        self.wake_word = self._load_wake_word()
        print(f"Wake word initialized to: {self.wake_word}")

    def _load_wake_word(self):
        """Loads the calibrated wake word from settings.json."""
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    return settings.get("wake_word", DEFAULT_WAKE_WORD).lower()
        except Exception as e:
            print(f"Error loading settings: {e}")
        return DEFAULT_WAKE_WORD.lower()

    def save_wake_word(self, word: str):
        """Saves the calibrated wake word to settings.json."""
        try:
            settings = {}
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)

            settings["wake_word"] = word.lower()
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=4)
            print(f"Calibration saved: {word}")
        except Exception as e:
            print(f"Error saving settings: {e}")

    def set_wake_word(self, word: str):
        """Updates the wake word based on calibration."""
        self.wake_word = word.lower()
        self.save_wake_word(word)
        print(f"Wake word updated to: {self.wake_word}")

    def collect_sample(self, timeout=5):
        """
        Captures a single utterance and returns the transcribed text.
        Used during calibration.
        """
        if self.model is None:
            return None

        print("Listening for a sample... Speak now!")

        # Temporary stream for a single sample
        try:
            with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                                   channels=1, callback=self._audio_callback):
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if not self.audio_queue.empty():
                        data = self.audio_queue.get()
                        if self.recognizer.AcceptWaveform(data):
                            result = json.loads(self.recognizer.Result())
                            text = result.get("text", "").lower()
                            if text:
                                return text

                # If we timeout, try to get the partial result
                result = json.loads(self.recognizer.FinalResult())
                return result.get("text", "").lower()
        except Exception as e:
            print(f"Error collecting sample: {e}")
            return None
        finally:
            # Clear queue to avoid bleed-over to main listening
            while not self.audio_queue.empty():
                self.audio_queue.get()

    def calibrate(self, samples_count=3, progress_callback=None):
        """
        Guides the user through saying the wake word multiple times
        and picks the most common transcription as the target.
        """
        message = f"Starting calibration. Please say your wake word {samples_count} times."
        print(message)
        if progress_callback:
            progress_callback(0, message)

        samples = []

        for i in range(samples_count):
            msg = f"Sample {i+1}/{samples_count}... Speak now!"
            print(msg)
            if progress_callback:
                progress_callback(i + 1, msg)

            text = self.collect_sample()
            if text:
                success_msg = f"Captured: {text}"
                print(success_msg)
                if progress_callback:
                    progress_callback(i + 1, success_msg)
                samples.append(text)
            else:
                fail_msg = "No speech detected. Try again."
                print(fail_msg)
                if progress_callback:
                    progress_callback(i + 1, fail_msg)
                # In a real scenario, we'd decrement i or loop until success

                # In a real scenario, we'd decrement i or loop until success

        if not samples:
            print("Calibration failed: No samples captured.")
            return False

        # Pick the most frequent transcription
        from collections import Counter
        most_common = Counter(samples).most_common(1)[0][0]

        print(f"Calibration complete. Best match found: {most_common}")
        self.set_wake_word(most_common)
        return True


    def _load_model(self):
        try:
            if not os.path.exists(MODEL_PATH):
                print("Downloading Vosk model... this may take a minute.")
                zip_path = "model.zip"
                urllib.request.urlretrieve(MODEL_URL, zip_path)
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    folder_name = zip_ref.namelist()[0].split('/')[0]
                    zip_ref.extractall(".")
                    os.rename(folder_name, MODEL_PATH)
                os.remove(zip_path)
                print("Model downloaded and extracted.")
            return Model(MODEL_PATH)
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to load Vosk model: {e}")
            # Return a dummy model or None to avoid crashing the rest of the app
            return None


    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        self.audio_queue.put(bytes(indata))

    def start_listening(self):
        if self.model is None:
            print("ASR Error: Model not loaded. Cannot start listening.")
            return

        self.is_listening = True
        try:
            with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                                   channels=1, callback=self._audio_callback):
                print(f"Listening for wake word: '{self.wake_word}'...")
                while self.is_listening:
                    data = self.audio_queue.get()
                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get("text", "").lower()
                        if text:
                            print(f"Heard: {text}")
                            # Use similarity instead of strict 'in' check
                            if self._similarity(text, self.wake_word) > 0.7:
                                if self.callback:
                                    self.callback(text)
        except Exception as e:
            print(f"ASR Stream Error: {e}")
            self.is_listening = False


    def stop_listening(self):
        self.is_listening = False

if __name__ == "__main__":
    # FIXED: Added 'event' argument to match the callback call
    def on_wake_word(event):
        print(f"\n>>> Vasco ACTIVATED via {event}! <<<\n")

    recognizer = SpeechRecognizer(callback_function=on_wake_word)
    try:
        recognizer.start_listening()
    except KeyboardInterrupt:
        print("Stopping...")
        recognizer.stop_listening()


