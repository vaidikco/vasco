"""The wake word must actually wake Vasco (the old code never could)."""

from vasco.core import WakeWordDetector

detector = WakeWordDetector("hey vasco")


def test_exact_match():
    woke, cmd = detector.match("hey vasco")
    assert woke and cmd == ""


def test_lowercased_asr_text_matches():
    # ASR output is lowercase; the old code searched for "hey Vasco" (capital V)
    woke, _ = detector.match("hey vasco")
    assert woke


def test_command_in_same_utterance():
    woke, cmd = detector.match("hey vasco open safari")
    assert woke and cmd == "open safari"


def test_name_only_wakes():
    woke, cmd = detector.match("vasco what time is it")
    assert woke and cmd == "what time is it"


def test_fuzzy_misheard_name():
    for heard in ("hey vasko", "hey basco", "a vasco open notes"):
        woke, _ = detector.match(heard)
        assert woke, f"should wake on {heard!r}"


def test_split_name_tokens():
    woke, cmd = detector.match("hey vas co open notes")
    assert woke and cmd == "open notes"


def test_observed_vosk_misrecognitions_wake_vasco():
    for heard in ("hey va go open notes", "he was go open notes",
                  "a verse go open notes"):
        woke, cmd = detector.match(heard)
        assert woke and cmd == "open notes", heard


def test_negatives():
    for heard in ("hey there", "the weather is nice", "velcro is handy",
                  "turn off the lights"):
        woke, _ = detector.match(heard)
        assert not woke, f"should NOT wake on {heard!r}"
