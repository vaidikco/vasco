"""Speech preparation stays display-friendly and natural to hear."""

from vasco.tts import TextToSpeech


def test_speech_cleanup_removes_display_markdown():
    text = "**Hello**\n- [Open YouTube](https://youtube.com)"
    assert TextToSpeech._prepare_for_speech(text) == "Hello. Open YouTube"


def test_default_voice_is_a_fast_microsoft_neural_voice():
    voice = TextToSpeech().voice
    # A Microsoft (Edge) en-US neural voice...
    assert voice.startswith("en-US-") and voice.endswith("Neural")
    # ...but NOT a "Multilingual" variant, which is ~4x slower to synthesize
    # and caused the long delay before Vasco started speaking.
    assert "Multilingual" not in voice
