"""Text-to-speech: Edge neural voices online, native OS voices offline.

Fixes over the original:
- Cross-platform playback. The old code used winsound (Windows-only) to play
  what edge-tts produces — which is actually MP3 data, something winsound
  can't decode anyway. Playback now uses afplay on macOS, ffplay/mpv when
  available elsewhere, and native offline voices as a last resort.
- The is_speaking race is gone: speak() marks is_speaking *before* the
  worker thread starts, so callers polling right after speak() see the truth.
- Temp audio files go to the system temp dir with unique names and get
  cleaned up, instead of overwriting "Vasco_response.wav" in the CWD.
"""

import asyncio
import logging
import re
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from vasco.config import config
from vasco import platform_utils as plat

logger = logging.getLogger("TTS")


class TextToSpeech:
    def __init__(self, voice: str | None = None):
        self.voice = voice or config.tts_voice
        self.rate = config.tts_rate
        self.pitch = config.tts_pitch
        self.volume = config.tts_volume
        self.is_speaking = False

    # -- public API ------------------------------------------------------------

    def speak(self, text: str):
        """Non-blocking: fire and forget."""
        self.is_speaking = True  # set BEFORE the thread starts (fixes the race)
        threading.Thread(target=self._speak_thread, args=(text,), daemon=True).start()

    def speak_blocking(self, text: str):
        """Blocking: returns when audio finishes. Call from a worker thread."""
        self.is_speaking = True
        try:
            self._speak_impl(text)
        finally:
            self.is_speaking = False

    def is_currently_speaking(self) -> bool:
        return self.is_speaking

    # -- implementation -----------------------------------------------------------

    def _speak_thread(self, text: str):
        try:
            self._speak_impl(text)
        finally:
            self.is_speaking = False

    def _speak_impl(self, text: str):
        text = self._prepare_for_speech(text)
        if not text:
            return
        try:
            audio_file = self._generate_edge_tts(text)
        except Exception as e:
            logger.warning("Edge-TTS failed (%s); using offline voice.", e)
            self._speak_offline(text)
            return
        try:
            self._play_file(audio_file)
        except Exception as e:
            logger.warning("Playback failed (%s); using offline voice.", e)
            self._speak_offline(text)
        finally:
            try:
                audio_file.unlink()
            except OSError:
                pass

    def _generate_edge_tts(self, text: str) -> Path:
        import edge_tts

        out = Path(tempfile.gettempdir()) / f"vasco_tts_{uuid.uuid4().hex}.mp3"

        async def _gen():
            communicate = edge_tts.Communicate(
                text,
                self.voice,
                rate=self.rate,
                pitch=self.pitch,
                volume=self.volume,
            )
            await communicate.save(str(out))

        asyncio.run(_gen())
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("edge-tts produced no audio")
        return out

    def _play_file(self, path: Path):
        # Universal, in-process playback: decode with soundfile (libsndfile,
        # which supports MP3) and play through sounddevice (PortAudio). Works on
        # macOS AND Windows with no external programs — so Windows also gets the
        # neural voice, not just the built-in SAPI fallback.
        try:
            import sounddevice as sd
            import soundfile as sf

            data, sr = sf.read(str(path), dtype="float32")
            sd.play(data, sr)
            sd.wait()
            return
        except Exception as e:
            logger.debug("In-process playback unavailable (%s); trying CLI players.", e)

        # Fallbacks: native / CLI players when present.
        if plat.IS_MACOS:
            subprocess.run(["afplay", str(path)], check=False)
            return
        for player, args in (
            ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
            ("mpv", ["--no-video", "--really-quiet"]),
            ("mpg123", ["-q"]),
        ):
            exe = plat.which(player)
            if exe:
                subprocess.run([exe, *args, str(path)], check=False)
                return
        raise RuntimeError("no usable audio playback method found")

    def _speak_offline(self, text: str):
        """Native OS voices — work with no internet and no extra packages."""
        try:
            if plat.IS_MACOS:
                subprocess.run(["say", "-v", config.tts_offline_voice, text], check=False)
            elif plat.IS_WINDOWS:
                script = (
                    "Add-Type -AssemblyName System.Speech; "
                    "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
                    f".Speak([Console]::In.ReadToEnd())"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", script],
                    input=text, text=True, check=False,
                )
            elif plat.which("espeak"):
                subprocess.run(["espeak", text], check=False)
            else:
                logger.error("No offline TTS available. Reply was: %s", text)
        except Exception as e:
            logger.error("Offline TTS failed: %s", e)

    @staticmethod
    def _prepare_for_speech(text: str) -> str:
        """Turn a display reply into a clean, naturally speakable sentence."""
        text = text.strip()
        # The brain is instructed not to use markdown, but this keeps an
        # occasional formatted answer from being read as punctuation.
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[`*_#]", "", text)
        text = re.sub(r"(?:^|\n)\s*[-•]\s+", ". ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tts = TextToSpeech()
    tts.speak_blocking("System check complete. Voice modules online and fully operational.")
    print("Speech finished.")
