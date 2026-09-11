from __future__ import annotations

import io
import wave

import sounddevice as sd
import speech_recognition as sr


class KevinSTT:
    def __init__(self):
        self.recognizer = sr.Recognizer()

        self.sample_rate = 16000
        self.channels = 1
        self.device = 1
        self.recording_time = 5.0

    def _record(self) -> bytes:
        print("\n🎙️ KEVIN is listening...")

        recording = sd.rec(
            int(self.recording_time * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            device=self.device,
        )

        sd.wait()

        wav_buffer = io.BytesIO()

        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(recording.tobytes())

        return wav_buffer.getvalue()

    def listen(self) -> str:
        try:
            audio_data = self._record()

            print("🧠 Processing...")

            audio = sr.AudioData(
                audio_data,
                self.sample_rate,
                2,
            )

            text = self.recognizer.recognize_google(
                audio,
                language="en-US",
            )

            print(f"📝 You said: {text}")

            return text.strip()

        except sr.UnknownValueError:
            print("KEVIN: I couldn't understand that.")
            return ""

        except sr.RequestError as error:
            print(f"KEVIN: Google STT error: {error}")
            return ""

        except KeyboardInterrupt:
            raise

        except Exception as error:
            print(f"KEVIN: STT error: {error}")
            return ""


stt = KevinSTT()


def listen() -> str:
    return stt.listen()