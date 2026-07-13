"""ASR wake-gate logic (hermetic — no Vosk/Whisper models loaded)."""

from vasco.asr import wake_hint_present


def test_clean_wake_word_passes_gate():
    assert wake_hint_present("hey vasco open safari", "vasco")


def test_vosk_manglings_still_pass_gate():
    # Rough Vosk transcripts that should still be flagged as "maybe the wake word"
    for heard in ("hey vasko open notes", "a vosco what time is it", "hey basco"):
        assert wake_hint_present(heard, "vasco"), heard


def test_ordinary_speech_does_not_pass_gate():
    for heard in ("what is the weather in tokyo", "play some music", "the box is red"):
        assert not wake_hint_present(heard, "vasco"), heard


def test_only_checks_first_few_words():
    # The wake word only matters near the start of an utterance.
    assert not wake_hint_present("one two three four five vasco", "vasco")
