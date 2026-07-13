import os
import sys
import json
import queue
import zipfile
import urllib.request
import sounddevice as sd
from vosk import Model, KaldiRecognizer

# Configuration
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_PATH = "model"
WAKE_WORD = "hey Vasco"

class SpeechRecognizer:
    def __init__(self, callback_function=None):
        self.callback = callback_function
        self.audio_queue = queue.Queue()
        self.model = self._load_model()
        self.recognizer = KaldiRecognizer(self.model, 16000)
        self.is_listening = False

    def _load_model(self):
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

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        self.audio_queue.put(bytes(indata))

    def start_listening(self):
        self.is_listening = True
        with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                               channels=1, callback=self._audio_callback):
            print(f"Listening for wake word: '{WAKE_WORD}'...")
            while self.is_listening:
                data = self.audio_queue.get()
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "").lower()
                    if text:
                        print(f"Heard: {text}")
                        if self.callback:
                            self.callback(text)

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


