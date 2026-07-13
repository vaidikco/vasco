"""Speech recognition — fast wake detection + accurate command transcription.

Two-layer design (best of both worlds, fully offline, Mac + Windows):

  * Vosk (bundled, tiny, real-time): always-on. It segments speech into
    utterances (knows when you stop talking) and provides the quick transcript
    used to spot the wake word. Cheap and instant.

  * faster-whisper (optional but recommended): when a command needs to be
    understood, the captured audio is re-transcribed with Whisper, which is
    dramatically more accurate (proper nouns, punctuation, accents). Runs on
    CPU on both macOS and Windows.

If faster-whisper isn't installed, Vosk handles everything — so the app still
runs anywhere. Set VASCO_ASR_ENGINE=vosk to force the light path.

Also:
  * pause()/resume() so Vasco doesn't hear itself while speaking.
  * All heavy imports are deferred so the rest of the package stays importable
    without audio/ML libraries.
"""

import json
import logging
import math
import os
import queue
import struct
import threading
import urllib.request
import zipfile
from difflib import SequenceMatcher
from pathlib import Path

from vasco.config import config

logger = logging.getLogger("ASR")

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
SAMPLE_RATE = 16000
# Smaller blocks = lower latency between speaking and Vasco reacting. 4000
# frames is 0.25s of audio (down from 0.5s).
BLOCK_SIZE = 4000
# When no speech is present, keep only this much trailing audio as pre-roll so
# the utterance buffer doesn't grow during silence.
_PREROLL_BYTES = int(SAMPLE_RATE * 0.3) * 2  # 0.3s of int16 mono


def wake_hint_present(text: str, wake_name: str) -> bool:
    """Cheap check: could this (rough Vosk) transcript plausibly say the wake word?

    Used to decide whether an idle utterance is worth the (more expensive)
    accurate Whisper transcription. Loose on purpose — Vosk mangles the name.
    """
    for word in text.split()[:5]:
        if SequenceMatcher(None, word, wake_name).ratio() >= 0.6:
            return True
    return False


class WhisperTranscriber:
    """Accurate offline transcription via faster-whisper (loaded in background)."""

    def __init__(self, model_name: str, compute_type: str):
        self.model_name = model_name
        self.compute_type = compute_type
        self._model = None
        self._ready = threading.Event()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            import numpy  # noqa: F401 - ensure the runtime dep is present
            from faster_whisper import WhisperModel

            logger.info("Loading Whisper model '%s' (first run downloads it)...", self.model_name)
            self._model = WhisperModel(
                self.model_name, device="cpu", compute_type=self.compute_type
            )
            self._ready.set()
            logger.info("Whisper model ready — high-accuracy transcription enabled.")
        except Exception as e:
            logger.warning("Whisper unavailable (%s); using Vosk transcripts only.", e)

    @property
    def ready(self) -> bool:
        return self._ready.is_set() and self._model is not None

    def transcribe(self, pcm_bytes: bytes) -> str:
        import numpy as np

        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size < SAMPLE_RATE * 0.2:  # < 0.2s, nothing worth transcribing
            return ""
        segments, _ = self._model.transcribe(
            audio, language="en", beam_size=1, vad_filter=True
        )
        return " ".join(s.text for s in segments).strip()


class SpeechRecognizer:
    def __init__(self, callback_function=None, model_path: Path | None = None,
                 level_callback=None):
        from vosk import KaldiRecognizer  # deferred import

        self.callback = callback_function
        # Optional callback(level: float 0..1) fired ~4x/sec with the live mic
        # loudness, so the UI can animate/"light up" while you speak.
        self.level_callback = level_callback
        self.audio_queue: queue.Queue = queue.Queue()
        self.model_path = Path(model_path or config.asr_model_path)
        self.model = self._load_model()
        self.recognizer = KaldiRecognizer(self.model, SAMPLE_RATE)
        self.is_listening = False
        self._paused = threading.Event()
        self._utterance = bytearray()

        # Wake-name used to decide when an idle utterance is worth the (more
        # expensive) accurate transcription.
        self._wake_name = config.wake_word.split()[-1].lower()
        # Set by the core: True while actively capturing a command (post-wake),
        # so commands are always transcribed at full accuracy.
        self.command_mode = False

        self.whisper = None
        if config.asr_engine in ("auto", "whisper"):
            self.whisper = WhisperTranscriber(config.whisper_model, config.whisper_compute)

    # -- model download / load ------------------------------------------------

    def _load_model(self):
        from vosk import Model

        if not self.model_path.exists():
            logger.info("Vosk model not found at %s — downloading (~40MB)...", self.model_path)
            zip_path = self.model_path.parent / "vosk-model.zip"
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(MODEL_URL, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                folder_name = zf.namelist()[0].split("/")[0]
                zf.extractall(self.model_path.parent)
            os.rename(self.model_path.parent / folder_name, self.model_path)
            zip_path.unlink()
            logger.info("Model downloaded and extracted.")
        return Model(str(self.model_path))

    # -- command mode (set by the core) --------------------------------------

    def set_command_mode(self, on: bool):
        self.command_mode = on

    # -- pause/resume (called from the core while TTS is playing) ------------

    def pause(self):
        self._paused.set()

    def resume(self):
        try:
            while True:
                self.audio_queue.get_nowait()
        except queue.Empty:
            pass
        self.recognizer.Reset()
        self._utterance.clear()
        self._paused.clear()

    # -- capture loop ------------------------------------------------------------

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug("Audio status: %s", status)
        self.audio_queue.put(bytes(indata))

    def _emit_level(self, data: bytes):
        """Compute RMS loudness of a block (0..1) and report it to the UI."""
        n = len(data) // 2
        if not n:
            return
        try:
            samples = struct.unpack(f"<{n}h", data[: n * 2])
            rms = math.sqrt(sum(s * s for s in samples) / n)
            self.level_callback(min(1.0, rms / 3000.0))
        except Exception:
            pass

    def _finalize(self, vosk_text: str):
        """Decide the best transcript for a completed utterance and dispatch it."""
        audio = bytes(self._utterance)
        self._utterance.clear()

        text = vosk_text
        # Use accurate (Whisper) transcription for: commands (post-wake), anything
        # that looks like it contains the wake word, and any SHORT idle utterance —
        # wake attempts are short, and Vosk often mangles the wake word, so this
        # dramatically improves how reliably "Hey Vasco …" is caught.
        word_count = len(vosk_text.split())
        want_accurate = (
            self.command_mode
            or wake_hint_present(vosk_text, self._wake_name)
            or 0 < word_count <= 6
        )
        if self.whisper and self.whisper.ready and want_accurate:
            try:
                accurate = self.whisper.transcribe(audio)
                if accurate:
                    text = accurate.strip().strip(".?!,").lower()
            except Exception as e:
                logger.warning("Whisper transcription failed (%s); using Vosk text.", e)

        if text and self.callback:
            logger.info("Heard: %s", text)
            self.callback(text)

    def start_listening(self):
        import sounddevice as sd  # deferred import

        self.is_listening = True
        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, dtype="int16",
                channels=1, latency="low", callback=self._audio_callback,
            ):
                logger.info("Listening for wake word: '%s'...", config.wake_word)
                while self.is_listening:
                    data = self.audio_queue.get()
                    if self._paused.is_set():
                        continue
                    if self.level_callback:
                        self._emit_level(data)
                    self._utterance += data
                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        vosk_text = result.get("text", "").strip().lower()
                        if vosk_text or self.command_mode:
                            self._finalize(vosk_text)
                        else:
                            self._utterance.clear()
                    else:
                        partial = json.loads(self.recognizer.PartialResult()).get("partial", "")
                        if not partial and len(self._utterance) > _PREROLL_BYTES:
                            # No speech yet — keep only a short pre-roll.
                            del self._utterance[:-_PREROLL_BYTES]
        except Exception as e:
            logger.error("Microphone stream failed: %s", e)
            logger.error("Voice input disabled. Check mic permissions/devices.")

    def stop_listening(self):
        self.is_listening = False
        self.audio_queue.put(b"")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    recognizer = SpeechRecognizer(callback_function=lambda t: print(f">>> {t}"))
    try:
        recognizer.start_listening()
    except KeyboardInterrupt:
        recognizer.stop_listening()
