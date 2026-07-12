import asyncio
import threading
import os
import winsound
import edge_tts

class TextToSpeech:
    def __init__(self, voice="en-US-ChristopherNeural"):
        # "en-US-ChristopherNeural" is a great, deep male voice for Vasco
        self.voice = voice
        self.output_file = "Vasco_response.wav"
        self.is_speaking = False

    async def _generate_and_play(self, text):
        try:
            self.is_speaking = True
            # 1. Generate audio using Edge-TTS
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(self.output_file)
            
            # 2. Play the wav file using Windows built-in sound
            winsound.PlaySound(self.output_file, winsound.SND_FILENAME)
        except Exception as e:
            print(f"Edge-TTS Error: {e}")
        finally:
            self.is_speaking = False

    def speak(self, text):
        """Public non-blocking method to trigger speech."""
        def run_async():
            asyncio.run(self._generate_and_play(text))
        
        threading.Thread(target=run_async, daemon=True).start()

    def is_currently_speaking(self):
        return self.is_speaking

# --- TEST HARNESS ---
if __name__ == "__main__":
    tts = TextToSpeech()
    test_phrase = "System check complete. Voice modules upgraded to Edge Neural. I am now fully operational and awaiting your command."
    print(f"Vasco is saying: {test_phrase}")
    tts.speak(test_phrase)
    
    import time
    while tts.is_currently_speaking():
        time.sleep(0.1)
    print("Speech finished.")

