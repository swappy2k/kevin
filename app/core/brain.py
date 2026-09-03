from openai import OpenAI
from dotenv import load_dotenv
import os

from app.core.personality import SYSTEM_PROMPT

load_dotenv()

client = OpenAI()

MODEL = os.getenv("MODEL", "gpt-5.5")


def ask_kevin(message: str):

    response = client.responses.create(
        model=MODEL,
        instructions=SYSTEM_PROMPT,
        input=message
    )

    return response.output_text