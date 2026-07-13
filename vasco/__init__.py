"""Vasco — a JARVIS-style desktop AI assistant.

Package layout:
    config          Environment-driven configuration
    core            The orchestrator state machine (headless, no Qt required)
    router          Local (Ollama) / cloud (Claude) brain with tool use
    actions         Cross-platform OS action registry
    executor        Sandboxed Python script execution
    memory          Markdown vault with semantic/keyword recall
    asr             Vosk speech recognition (wake word)
    tts             Edge-TTS voice with offline fallbacks
    ocr             Screen reading (optional, needs easyocr)
    ui              PyQt6 Dynamic Island shell
"""

__version__ = "0.2.0"
