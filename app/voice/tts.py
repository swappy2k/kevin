import pyttsx3


class KevinTTS:
    def __init__(self):
        self.engine = pyttsx3.init("sapi5")
        self.engine.setProperty("volume", 1.0)
        self.engine.setProperty("rate", 175)

        voices = self.engine.getProperty("voices")

        if voices:
            self.engine.setProperty("voice", voices[0].id)

    def speak(self, text: str):
        if not text:
            return

        self.engine.say(text)
        self.engine.runAndWait()


tts = KevinTTS()


def speak(text: str):
    tts.speak(text)