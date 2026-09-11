from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("sk-proj-Sdl0k6IMGLS4Wu_K3tX1yykgBjPa4lL10LP78SRsgLPEEv7UxvTs1xaBX-BClBvUROjIEY")
)

MODEL = os.getenv("MODEL", "gpt-5.5")