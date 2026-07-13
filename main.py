"""Vasco entry point.

Usage:
    python main.py            # full experience: island UI + voice in/out
    python main.py --text     # headless text REPL (no mic, speakers, or Qt)
    python main.py --no-tts   # UI + voice recognition, replies as text only
"""

import argparse
import asyncio
import sys
import threading


def run_text_mode():
    """Headless REPL — great for development and machines without a mic."""
    from vasco.core import VascoCore

    core = VascoCore()  # NullSignals, no TTS

    async def repl():
        core.loop = asyncio.get_running_loop()
        print("Vasco text mode. Type a command ('exit' to quit).")
        print("Try: 'what time is it', 'open safari', 'remember that ...', or any question.\n")
        while True:
            try:
                line = await asyncio.to_thread(input, "you> ")
            except (EOFError, KeyboardInterrupt):
                break
            line = line.strip()
            if not line:
                continue
            if line.lower() in {"exit", "quit", "bye"}:
                break
            reply = await core.process_command(line)
            print(f"vasco> {reply}\n")
        print("Goodbye.")

    asyncio.run(repl())


def run_voice_mode(with_tts: bool = True):
    from PyQt6.QtWidgets import QApplication

    from vasco.ui import CoreWorker, DynamicIsland, VascoSignals

    app = QApplication(sys.argv)
    signals = VascoSignals()

    tts = None
    if with_tts:
        from vasco.tts import TextToSpeech
        tts = TextToSpeech()

    worker = CoreWorker(signals=signals, tts=tts)

    island = DynamicIsland(
        signals=signals,
        on_activate=worker.core.trigger_listening,
        on_submit=worker.core.submit_command,
        on_toggle_continuous=worker.core.set_continuous,
    )
    island.show()

    worker.start()

    # Voice input (optional at runtime: Vasco still works via island click + text)
    try:
        from vasco.asr import SpeechRecognizer

        recognizer = SpeechRecognizer(
            callback_function=worker.core.handle_asr_result,
            level_callback=lambda lvl: signals.audio_level.emit(lvl),
        )
        worker.core.asr = recognizer
        asr_thread = threading.Thread(target=recognizer.start_listening, daemon=True)
        asr_thread.start()
    except Exception as e:
        print(f"Voice input unavailable ({e}). Click the island to activate Vasco.")

    exit_code = app.exec()
    worker.stop()
    sys.exit(exit_code)


def main():
    parser = argparse.ArgumentParser(description="Vasco — a JARVIS-style desktop assistant")
    parser.add_argument("--text", action="store_true", help="headless text REPL mode")
    parser.add_argument("--no-tts", action="store_true", help="don't speak replies aloud")
    args = parser.parse_args()

    if args.text:
        run_text_mode()
    else:
        run_voice_mode(with_tts=not args.no_tts)


if __name__ == "__main__":
    main()
