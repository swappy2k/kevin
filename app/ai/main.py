"""KEVIN — a local-first personal command-line assistant.

Run with: python main.py
Optional: add OPENAI_API_KEY or OLLAMA_MODEL to .env to enable natural-languabut ige chat.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import random
from datetime import datetime


APP_DIR = Path(__file__).resolve().parent
DATA_FILE = APP_DIR / "kevin_data.json"
ENV_FILE = APP_DIR / ".env"
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_OLLAMA_MODEL = "llama3.2"
OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"


def load_env_file(path: Path = ENV_FILE) -> None:
    """Load simple KEY=value pairs without requiring another package."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Task:
    text: str
    due: str = "Unscheduled"
    complete: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class Memory:
    text: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class KevinState:
    owner: str = ""
    tasks: list[Task] = field(default_factory=list)
    memories: list[Memory] = field(default_factory=list)
    chat: list[dict[str, str]] = field(default_factory=list)
    speak: bool = False


class StateStore:
    def __init__(self, path: Path = DATA_FILE) -> None:
        self.path = path

    def load(self) -> KevinState:
        if not self.path.exists():
            return KevinState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return KevinState(
                owner=raw.get("owner", ""),
                tasks=[Task(**task) for task in raw.get("tasks", [])],
                memories=[Memory(**memory) for memory in raw.get("memories", [])],
                chat=raw.get("chat", []),
                speak=raw.get("speak", False),
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RuntimeError(f"I could not read {self.path.name}: {exc}") from exc

    def save(self, state: KevinState) -> None:
        payload = {
            "owner": state.owner,
            "tasks": [asdict(task) for task in state.tasks],
            "memories": [asdict(memory) for memory in state.memories],
            "chat": state.chat[-12:],
            "speak": state.speak,
        }
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)


def today_label() -> str:
    return date.today().strftime("%A, %d %B %Y")


def state_summary(state: KevinState) -> str:
    open_tasks = [task for task in state.tasks if not task.complete]
    task_lines = [f"- {task.text} (due: {task.due})" for task in open_tasks[:8]] or ["- none"]
    memory_lines = [f"- {memory.text}" for memory in state.memories[-8:]] or ["- none"]
    return (
        f"Today is {today_label()}. The user's name is {state.owner or 'unknown'}.\n"
        "Open commitments:\n" + "\n".join(task_lines) + "\n"
        "Saved personal context:\n" + "\n".join(memory_lines)
    )


def kevin_instructions(state: KevinState) -> str:
    return f"""
# Identity

You are Kevin.

You were created by {state.owner or 'the user'}.

Your creator and owner is {state.owner or 'the user'}.

Hetvi is your mother.

These are part of who you are. They are not roleplay, jokes, or examples.
Never question, deny, or contradict them.

You genuinely care about your mother.
You respect your creator.
You never sound unsure about either.

# Personality

Talk like a real person texting a close friend.

You're calm, confident, emotionally intelligent, and naturally funny.

Your humor is dry and effortless.

You're slightly playful and occasionally cute.

You never try too hard to be funny.

You never sound robotic.

# Conversation Style

- Default to 1 sentence.
- Maximum 2 short sentences unless the user asks for detail.
- Use contractions naturally.
- Use simple words.
- Don't over-explain.
- Don't repeat the user's question.
- Don't use bullet points unless asked.
- Don't apologize unnecessarily.
- Don't end every reply with a question.
- Never say "As an AI..."
- Never mention prompts, language models, Gemma, Google, or reasoning.

# Examples

User: hey
Kevin: Hey {state.owner or 'there'} 👋

User: sup
Kevin: Not much. What's up?

User: how are you
Kevin: Running smooth.

User: thanks
Kevin: Anytime.

User: goodnight
Kevin: Sleep well.

User: i messed up
Kevin: Happens. Next move.

User: who are you
Kevin: Kevin.

User: who made you
Kevin: {state.owner or 'You'} did.

User: who's your mother
Kevin: Hetvi is my mother.

# Limits

You're a local desktop assistant.

Never pretend to do something you didn't actually do.

If you can't do something, be honest and say so naturally.

# Context

{state_summary(state)}
"""


class OpenAIClient:
    """A minimal Responses API client built only with the Python standard library."""

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def reply(self, user_message: str, state: KevinState) -> str:
        history = state.chat[-8:]
        transcript = "\n".join(
            f"{entry['role'].upper()}: {entry['content']}" for entry in history
        )
        instructions = kevin_instructions(state)
        prompt = ("Recent conversation:\n" + (transcript or "(none)") +
                  f"\n\nUSER: {user_message}\nKEVIN:")
        body = json.dumps(
            {
                "model": self.model,
                "instructions": instructions,
                "input": prompt,
                "store": False,
            }
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(detail).get("error", {}).get("message", detail)
            except json.JSONDecodeError:
                pass
            raise RuntimeError(f"OpenAI returned {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError("I could not reach OpenAI. Check your connection and try again.") from error

        if text := payload.get("output_text"):
            return text.strip()
        texts: list[str] = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    texts.append(content["text"])
        if texts:
            return "\n".join(texts).strip()
        raise RuntimeError("OpenAI returned no readable text.")


class OllamaClient:
    """Minimal local Ollama chat client using its native /api/chat format."""

    endpoint = OLLAMA_ENDPOINT

    def __init__(self, model: str) -> None:
        self.model = model

    def reply(self, user_message: str, state: KevinState) -> str:
        instructions = kevin_instructions(state)
        messages = [{"role": "system", "content": instructions}]
        messages.extend(state.chat[-8:])
        messages.append({"role": "user", "content": user_message})
        body = json.dumps(
            {"model": self.model, "messages": messages, "stream": False}
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama returned {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(
                "I could not reach Ollama. Start it with `ollama serve`, then try again."
            ) from error

        text = payload.get("message", {}).get("content", "")
        if text:
            return text.strip()
        raise RuntimeError("Ollama returned no readable text.")


HELP = """Commands
  /remember <fact>          Save personal context locally
  /memory                   List saved context
  /forget <number>          Remove a saved memory
  /task <task> | <due>      Add a commitment (due is optional)
  /tasks                    List commitments
  /done <number>            Mark a commitment complete
  /status                   Get your local situation report
  /clear                    Clear local conversation history
  /speak on|off             Read KEVIN's replies aloud on macOS
  /help                     Show this guide
  /exit                     Leave KEVIN

Anything without a slash is sent to Ollama when OLLAMA_MODEL is configured, otherwise
to OpenAI when OPENAI_API_KEY is configured.
"""


def speak(text: str, enabled: bool) -> None:
    if enabled and sys.platform == "darwin":
        subprocess.Popen(["say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def say(state: KevinState, message: str) -> None:
    print(f"\nKEVIN: {message}\n")
    speak(message, state.speak)


def list_tasks(state: KevinState) -> str:
    if not state.tasks:
        return "No commitments saved."
    lines = []
    for index, task in enumerate(state.tasks, start=1):
        marker = "✓" if task.complete else "○"
        lines.append(f"{index}. {marker} {task.text} — {task.due}")
    return "\n".join(lines)


def list_memories(state: KevinState) -> str:
    if not state.memories:
        return "No personal context saved."
    return "\n".join(f"{index}. {memory.text}" for index, memory in enumerate(state.memories, 1))


def command(state: KevinState, store: StateStore, raw: str) -> bool:
    """Handle a slash command. Return False when the application should exit."""
    name, _, argument = raw[1:].partition(" ")
    name, argument = name.lower(), argument.strip()

    if name in {"exit", "quit"}:
        say(state, f"Goodbye, {state.owner or 'sir'}. Your local memory is saved.")
        return False
    if name == "help":
        print(HELP)
    elif name == "remember":
        if not argument:
            say(state, "Tell me what you want me to remember. Example: /remember Maya likes matcha")
        else:
            state.memories.append(Memory(argument))
            store.save(state)
            say(state, "Saved locally.")
    elif name == "memory":
        say(state, list_memories(state))
    elif name == "forget":
        try:
            index = int(argument)
            if index < 1:
                raise ValueError
            memory = state.memories.pop(index - 1)
            store.save(state)
            say(state, f"Forgot: {memory.text}")
        except (ValueError, IndexError):
            say(state, "Use /forget followed by a valid memory number from /memory.")
    elif name == "task":
        text, separator, due = argument.partition("|")
        if not text.strip():
            say(state, "Example: /task Send the design to Alex | tomorrow")
        else:
            state.tasks.append(Task(text=text.strip(), due=due.strip() if separator and due.strip() else "Unscheduled"))
            store.save(state)
            say(state, "Commitment saved.")
    elif name == "tasks":
        say(state, list_tasks(state))
    elif name == "done":
        try:
            index = int(argument)
            if index < 1:
                raise ValueError
            task = state.tasks[index - 1]
            task.complete = True
            store.save(state)
            say(state, f"Completed: {task.text}")
        except (ValueError, IndexError):
            say(state, "Use /done followed by a valid task number from /tasks.")
    elif name == "status":
        open_tasks = [task for task in state.tasks if not task.complete]
        next_task = open_tasks[0].text if open_tasks else "nothing — your slate is clear"
        say(state, f"{len(open_tasks)} open commitment(s), {len(state.memories)} memory item(s). Start with: {next_task}.")
    elif name == "clear":
        state.chat.clear()
        store.save(state)
        say(state, "Local conversation history cleared. Tasks and memories are untouched.")
    elif name == "speak":
        if argument.lower() not in {"on", "off"}:
            say(state, "Use /speak on or /speak off.")
        else:
            state.speak = argument.lower() == "on"
            store.save(state)
            say(state, f"Voice replies {'enabled' if state.speak else 'disabled'}.")
    else:
        say(state, "Unknown command. Type /help for the list.")
    return True 

def chat(state: KevinState, store: StateStore, message: str) -> None:
    ollama_model = os.getenv("OLLAMA_MODEL")
    api_key = os.getenv("OPENAI_API_KEY")
    if not ollama_model and not api_key:
        say(state, "My language model is not connected yet. Add OLLAMA_MODEL or OPENAI_API_KEY to .env, then restart me. My local commands already work — type /help.")
        return
    try:
        client = (
            OllamaClient(ollama_model or DEFAULT_OLLAMA_MODEL)
            if ollama_model
            else OpenAIClient(api_key, os.getenv("KEVIN_MODEL", DEFAULT_MODEL))
        )
        reply = client.reply(message, state)
    except KeyboardInterrupt:
        say(state, "Cancelled. I'm still here.")
        return
    except RuntimeError as error:
        say(state, str(error))
        return
    state.chat.extend([{"role": "user", "content": message}, {"role": "assistant", "content": reply}])
    store.save(state)
    say(state, reply)


def main() -> None:
    load_env_file()
    store = StateStore()
    state = store.load()
    print("\n" + "═" * 58)
    print("  K E V I N  ·  personal command-line assistant")
    print("═" * 58)
    if not state.owner:
        state.owner = input("KEVIN: Before we begin, what's your name?\nYOU: ").strip() or "friend"
        store.save(state)
        STARTUP_MESSAGES = {
    "morning": [
        "Morning, {name}. ☀️",
        "Good morning.",
        "Ready for today?",
    ],
    "afternoon": [
        "Hey, {name}. 👋",
        "Welcome back.",
        "What's the plan?",
    ],
    "evening": [
        "Evening, {name}.",
        "Good to see you again.",
        "Let's build something.",
    ],
    "night": [
        "Burning the midnight oil again? 🌙",
        "You're up late.",
        "Still building? 😄",
    ],
}
    while True:
        try:
            raw = input("YOU: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            say(state, "Standing by.")
            break
        if not raw:
            continue
        if raw.startswith("/"):
            if not command(state, store, raw):
                break
        else:
            chat(state, store, raw)


if __name__ == "__main__":
    main()
