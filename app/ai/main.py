"""
KEVIN — a local-first personal command-line assistant.

Run with: python app/ai/main.py
Optional: add OPENAI_API_KEY or OLLAMA_MODEL to .env to enable natural-language chat.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Allow both `python app/ai/main.py` and `python -m app.ai.main`.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


from dotenv import load_dotenv
from app.tools.browser import search as browser_search
from app.tools.calendar import CalendarEvent, calendar as local_calendar
from app.voice.tts import speak as tts_speak
from app.voice.stt import listen as stt_listen


# ---------------------------------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------------------------------

load_dotenv(r"C:\Users\yuvraj\Desktop\kevin\.env")


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

        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------------------------

@dataclass
class Task:
    text: str
    due: str = "Unscheduled"
    complete: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


@dataclass
class Memory:
    text: str
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


@dataclass
class KevinState:
    owner: str = ""
    tasks: list[Task] = field(default_factory=list)
    memories: list[Memory] = field(default_factory=list)
    chat: list[dict[str, str]] = field(default_factory=list)
    speak: bool = True


# ---------------------------------------------------------------------------
# STATE STORAGE
# ---------------------------------------------------------------------------

class StateStore:
    def __init__(self, path: Path = DATA_FILE) -> None:
        self.path = path

    def load(self) -> KevinState:
        if not self.path.exists():
            return KevinState()

        try:
            raw = json.loads(
                self.path.read_text(encoding="utf-8")
            )

            return KevinState(
                owner=raw.get("owner", ""),
                tasks=[
                    Task(**task)
                    for task in raw.get("tasks", [])
                ],
                memories=[
                    Memory(**memory)
                    for memory in raw.get("memories", [])
                ],
                chat=raw.get("chat", []),
                speak=raw.get("speak", False),
            )

        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"I could not read {self.path.name}: {exc}"
            ) from exc

    def save(self, state: KevinState) -> None:
        payload = {
            "owner": state.owner,
            "tasks": [asdict(task) for task in state.tasks],
            "memories": [asdict(memory) for memory in state.memories],
            "chat": [],
            "speak": state.speak,
        }

        temporary = self.path.with_suffix(".tmp")

        temporary.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

        temporary.replace(self.path)


# ---------------------------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------------------------

def today_label() -> str:
    return date.today().strftime("%A, %d %B %Y")


def state_summary(state: KevinState) -> str:
    open_tasks = [
        task
        for task in state.tasks
        if not task.complete
    ]

    task_lines = [
        f"- {task.text} (due: {task.due})"
        for task in open_tasks[:8]
    ] or ["- none"]

    memory_lines = [
        f"- {memory.text}"
        for memory in state.memories[-8:]
    ] or ["- none"]

    return (
        f"Today is {today_label()}. "
        f"The user's name is {state.owner or 'unknown'}.\n"
        "Open commitments:\n"
        + "\n".join(task_lines)
        + "\n"
        + "Saved personal context:\n"
        + "\n".join(memory_lines)
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
- Reply in English unless the current message explicitly asks for another language.
- Never infer a language preference from earlier messages, a name, location, or a speech-recognition mistake.
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


# ---------------------------------------------------------------------------
# OPENAI CLIENT
# ---------------------------------------------------------------------------

class OpenAIClient:
    """A minimal Responses API client built only with the Python standard library."""

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def reply(self, user_message: str, state: KevinState) -> str:
        history = state.chat[-8:]

        transcript = "\n".join(
            f"{entry['role'].upper()}: {entry['content']}"
            for entry in history
        )

        instructions = kevin_instructions(state)

        prompt = (
            "Recent conversation:\n"
            + (transcript or "(none)")
            + f"\n\nUSER: {user_message}\nKEVIN:"
        )

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
                payload: dict[str, Any] = json.loads(
                    response.read().decode("utf-8")
                )

        except HTTPError as error:
            detail = error.read().decode(
                "utf-8",
                errors="replace",
            )

            try:
                detail = json.loads(detail).get(
                    "error",
                    {},
                ).get(
                    "message",
                    detail,
                )
            except json.JSONDecodeError:
                pass

            raise RuntimeError(
                f"OpenAI returned {error.code}: {detail}"
            ) from error

        except URLError as error:
            raise RuntimeError(
                "I could not reach OpenAI. "
                "Check your connection and try again."
            ) from error

        if text := payload.get("output_text"):
            return text.strip()

        texts: list[str] = []

        for item in payload.get("output", []):
            for content in item.get("content", []):
                if (
                    content.get("type") == "output_text"
                    and content.get("text")
                ):
                    texts.append(content["text"])

        if texts:
            return "\n".join(texts).strip()

        raise RuntimeError(
            "OpenAI returned no readable text."
        )


# ---------------------------------------------------------------------------
# OLLAMA CLIENT
# ---------------------------------------------------------------------------

class OllamaClient:
    """Minimal local Ollama chat client."""

    endpoint = OLLAMA_ENDPOINT

    def __init__(self, model: str) -> None:
        self.model = model

    def reply(self, user_message: str, state: KevinState) -> str:
        instructions = kevin_instructions(state)

        messages = [
            {
                "role": "system",
                "content": instructions,
            }
        ]

        messages.extend(state.chat[-8:])

        messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
            }
        ).encode("utf-8")

        request = Request(
            self.endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=60) as response:
                payload: dict[str, Any] = json.loads(
                    response.read().decode("utf-8")
                )

        except HTTPError as error:
            detail = error.read().decode(
                "utf-8",
                errors="replace",
            )

            raise RuntimeError(
                f"Ollama returned {error.code}: {detail}"
            ) from error

        except URLError as error:
            raise RuntimeError(
                "I could not reach Ollama. "
                "Start it with `ollama serve`, then try again."
            ) from error

        text = payload.get(
            "message",
            {},
        ).get(
            "content",
            "",
        )

        if text:
            return text.strip()

        raise RuntimeError(
            "Ollama returned no readable text."
        )


# ---------------------------------------------------------------------------
# HELP / COMMANDS
# ---------------------------------------------------------------------------

HELP = """Commands
/remember <fact>          Save personal context locally
/memory                   List saved context
/forget <number>          Remove a saved memory
/task <task> | <due>      Add a commitment (due is optional)
/tasks                    List commitments
/done <number>            Mark a commitment complete
/status                   Get your local situation report
/clear                    Clear local conversation history
/speak on|off             Read KEVIN's replies aloud
/listen                   Start continuous voice mode
/stop                     Shut KEVIN down
/event <title> | <date>   Add a local event (date: YYYY-MM-DD HH:MM)
/calendar                 List upcoming local events
/available <date> <time>  Check if a time is free
/free <date>              Show free hourly slots
/cancel-event <id>        Remove a local event
/help                     Show this guide
/exit                     Leave KEVIN

Voice mode starts automatically. Say "search for <topic>" to search Google,
or say "stop listening" to return to the keyboard. Type "start listening"
to resume voice mode. Say or type "stop" to shut KEVIN down.

Voice calendar examples:
"schedule a calendar event Test Meeting on 2026-09-11 at 15:00"
"am I free 2026-09-11 at 15:00"
"what time am I free on 2026-09-11"
"show my calendar"
"cancel event 2"
"cancel events 1 and 2"
"cancel all events"

Date examples:
what day is today
what date is today
what day is 15/09/2026

Anything without a slash is sent to Ollama when OLLAMA_MODEL is configured,
otherwise to OpenAI when OPENAI_API_KEY is configured.
"""


# ---------------------------------------------------------------------------
# SEARCH / VOICE REGEX
# ---------------------------------------------------------------------------

SEARCH_COMMAND = re.compile(
    r"^\s*(?:kevin[,:]?\s+)?(?:search(?:\s+(?:for|on google))?|"
    r"google|look up|find)\s+(.+?)\s*$",
    re.IGNORECASE,
)


NEWS_REQUEST = re.compile(
    r"\b(?:latest|today(?:'s)?|current|recent)?\s*news\b",
    re.IGNORECASE,
)


SPOKEN_FILLER = re.compile(
    r"^\s*(?:kevin[,:]?\s+|please\s+|mujhe\s+|isko\s+|is ko\s+)",
    re.IGNORECASE,
)


VOICE_START_COMMANDS = {
    "start listening",
    "start voice mode",
    "listen kevin",
}


VOICE_STOP_COMMANDS = {
    "exit voice mode",
    "stop listening",
    "stop voice mode",
    "goodbye kevin",
}


APP_STOP_COMMANDS = {
    "stop",
    "exit",
    "quit",
}


CALENDAR_CREATE_COMMAND = re.compile(
    r"^\s*(?:add|create|schedule)\s+(?:an?\s+)?(?:calendar\s+)?"
    r"(?:event\s+)?(.+?)\s+(?:on|at)\s+"
    r"(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})\s*$",
    re.IGNORECASE,
)


# Natural spoken calendar commands.
SPOKEN_EVENT_COMMAND = re.compile(
    r"^\s*(?:schedule|create|add|book)\s+"
    r"(?:a\s+)?"
    r"(?:calendar\s+)?"
    r"(?:event\s+)?"
    r"(.+?)\s+"
    r"(?:on\s+)?"
    r"(\d{4}-\d{2}-\d{2})\s+"
    r"(?:at\s+)?"
    r"(\d{1,2}:\d{2})\s*$",
    re.IGNORECASE,
)


SPOKEN_AVAILABLE_COMMAND = re.compile(
    r"^\s*(?:am\s+i|is\s+my\s+schedule)\s+free\s+"
    r"(?:on\s+)?"
    r"(\d{4}-\d{2}-\d{2})\s+"
    r"(?:at\s+)?"
    r"(\d{1,2}:\d{2})\s*$",
    re.IGNORECASE,
)


SPOKEN_FREE_COMMAND = re.compile(
    r"^\s*(?:what\s+time\s+am\s+i\s+free|"
    r"when\s+am\s+i\s+free|"
    r"show\s+my\s+free\s+time)\s+"
    r"(?:on\s+)?"
    r"(\d{4}-\d{2}-\d{2})\s*$",
    re.IGNORECASE,
)


# FIXED:
# Accept one event, multiple event IDs, or "all".
#
# Examples:
#   cancel event 1
#   cancel events 1 and 2
#   cancel 1, 2
#   delete event 3
#   remove all events
#   cancel all events
#
SPOKEN_CANCEL_EVENT = re.compile(
    r"^\s*(?:cancel|delete|remove)\s+"
    r"(?:(?:the\s+)?(?:event|events)\s+)?"
    r"(.+?)\s*$",
    re.IGNORECASE,
)


CALENDAR_LIST_COMMANDS = {
    "calendar",
    "show calendar",
    "show my calendar",
    "my calendar",
    "show my",
    "upcoming events",
    "what's on my calendar",
    "what is on my calendar",
}


TIME_REQUEST = re.compile(
    r"^\s*(?:what(?:'s| is)\s+(?:the\s+)?time(?:\s+right\s+now)?|"
    r"(?:what\s+time\s+is\s+it|current\s+time|time(?:\s+right\s+now)?|"
    r"tell\s+me\s+(?:the\s+)?time))\s*[.?!]*\s*$",
    re.IGNORECASE,
)


def search_query(message: str) -> str | None:
    """Infer a web query from an explicit or natural spoken search request."""

    match = SEARCH_COMMAND.match(message)

    if match:
        return match.group(1).strip(" .?!") or None

    if NEWS_REQUEST.search(message):
        query = SPOKEN_FILLER.sub("", message).strip(" .?!")
        return query or "latest news"

    return None


def format_calendar(events: list[CalendarEvent]) -> str:
    if not events:
        return "Your calendar is clear."

    return "\n".join(
        f"{event.id}. "
        f"{event.starts_at.strftime('%a, %d %b at %I:%M %p')} — "
        f"{event.title}"
        for event in events
    )


def current_time_reply() -> str:
    return f"It's {datetime.now().strftime('%I:%M %p').lstrip('0')}."


def date_day_reply(message: str) -> str | None:
    text = message.lower().strip(" .?!")

    if text in {
        "what day is today",
        "what day is it today",
        "which day is today",
        "which day is it today",
    }:
        return datetime.now().strftime("Today is %A.")

    if text in {
        "what date is today",
        "what is today's date",
        "what's today's date",
        "which date is today",
    }:
        return datetime.now().strftime("Today is %d %B %Y.")

    match = re.search(
        r"what day is (\d{1,2})[/-](\d{1,2})[/-](\d{4})",
        text,
    )

    if match:
        day, month, year = map(int, match.groups())

        try:
            result = date(year, month, day)

            return result.strftime(
                "%d %B %Y is a %A."
            )

        except ValueError:
            return "That isn't a valid date."

    return None


def say(
    state: KevinState,
    message: str,
) -> None:
    print(
        f"\nKEVIN: {message}\n"
    )

    if state.speak:
        tts_speak(message)


# ---------------------------------------------------------------------------
# TASK / MEMORY HELPERS
# ---------------------------------------------------------------------------

def list_tasks(
    state: KevinState,
) -> str:
    if not state.tasks:
        return "No commitments saved."

    lines = []

    for index, task in enumerate(
        state.tasks,
        start=1,
    ):
        marker = "✓" if task.complete else "○"

        lines.append(
            f"{index}. {marker} {task.text} — {task.due}"
        )

    return "\n".join(lines)


def list_memories(
    state: KevinState,
) -> str:
    if not state.memories:
        return "No personal context saved."

    return "\n".join(
        f"{index}. {memory.text}"
        for index, memory in enumerate(
            state.memories,
            1,
        )
    )


# ---------------------------------------------------------------------------
# VOICE LOOP
# ---------------------------------------------------------------------------

def voice_loop(
    state: KevinState,
    store: StateStore,
) -> bool:
    """Listen for spoken requests. Return False when KEVIN should exit."""

    while True:
        message = stt_listen()

        if not message:
            continue

        spoken_command = message.lower().strip(" .?!")

        if spoken_command in APP_STOP_COMMANDS:
            say(
                state,
                "Stopping now.",
            )
            return False

        if spoken_command in VOICE_STOP_COMMANDS:
            say(
                state,
                "Voice mode disabled.",
            )
            return True

        if spoken_command in VOICE_START_COMMANDS:
            say(
                state,
                "I'm already listening.",
            )
            continue

        if message.startswith("/"):
            if not command(
                state,
                store,
                message,
            ):
                return False
        else:
            chat(
                state,
                store,
                message,
            )


# ---------------------------------------------------------------------------
# SLASH COMMAND HANDLER
# ---------------------------------------------------------------------------

def command(
    state: KevinState,
    store: StateStore,
    raw: str,
) -> bool:
    """Handle a slash command."""

    name, _, argument = raw[1:].partition(" ")

    name = name.lower()
    argument = argument.strip()

    # -----------------------------------------------------------------------
    # EXIT
    # -----------------------------------------------------------------------

    if name in {
        "exit",
        "quit",
        "stop",
    }:
        say(
            state,
            f"Goodbye, {state.owner or 'sir'}. "
            "Your local memory is saved.",
        )
        return False

    # -----------------------------------------------------------------------
    # HELP
    # -----------------------------------------------------------------------

    if name == "help":
        say(
            state,
            HELP,
        )

    # -----------------------------------------------------------------------
    # REMEMBER
    # -----------------------------------------------------------------------

    elif name == "remember":
        if not argument:
            say(
                state,
                "Tell me what you want me to remember. "
                "Example: /remember Maya likes matcha",
            )
        else:
            state.memories.append(
                Memory(argument)
            )

            store.save(state)

            say(
                state,
                "Saved locally.",
            )

    # -----------------------------------------------------------------------
    # MEMORY
    # -----------------------------------------------------------------------

    elif name == "memory":
        say(
            state,
            list_memories(state),
        )

    # -----------------------------------------------------------------------
    # FORGET
    # -----------------------------------------------------------------------

    elif name == "forget":
        try:
            index = int(argument)

            if index < 1:
                raise ValueError

            memory = state.memories.pop(
                index - 1
            )

            store.save(state)

            say(
                state,
                f"Forgot: {memory.text}",
            )

        except (
            ValueError,
            IndexError,
        ):
            say(
                state,
                "Use /forget followed by a valid "
                "memory number from /memory.",
            )

    # -----------------------------------------------------------------------
    # TASK
    # -----------------------------------------------------------------------

    elif name == "task":
        text, separator, due = argument.partition("|")

        if not text.strip():
            say(
                state,
                "Example: /task Send the design to Alex | tomorrow",
            )
        else:
            state.tasks.append(
                Task(
                    text=text.strip(),
                    due=(
                        due.strip()
                        if separator and due.strip()
                        else "Unscheduled"
                    ),
                )
            )

            store.save(state)

            say(
                state,
                "Commitment saved.",
            )

    # -----------------------------------------------------------------------
    # CREATE EVENT
    # -----------------------------------------------------------------------

    elif name == "event":
        title, separator, starts_at = argument.partition("|")

        if not separator:
            say(
                state,
                "Use /event <title> | YYYY-MM-DD HH:MM. "
                "Example: /event Dentist | 2026-09-10 14:30",
            )
        else:
            try:
                event = local_calendar.add_event(
                    title,
                    starts_at,
                )

            except (
                RuntimeError,
                ValueError,
            ) as error:
                say(
                    state,
                    str(error),
                )

            else:
                say(
                    state,
                    f"Added event {event.id}: "
                    f"{event.title} on {event.starts_at}.",
                )

    # -----------------------------------------------------------------------
    # CALENDAR
    # -----------------------------------------------------------------------

    elif name == "calendar":
        try:
            say(
                state,
                format_calendar(
                    local_calendar.upcoming()
                ),
            )

        except RuntimeError as error:
            say(
                state,
                str(error),
            )

    # -----------------------------------------------------------------------
    # AVAILABILITY
    # -----------------------------------------------------------------------

    elif name == "available":
        try:
            start = local_calendar.parse_datetime(
                argument
            )

            if local_calendar.is_available(start):
                say(
                    state,
                    "You're free at "
                    f"{start.strftime('%d %B %Y at %I:%M %p').lstrip('0')}.",
                )
            else:
                say(
                    state,
                    "You're already booked at "
                    f"{start.strftime('%d %B %Y at %I:%M %p').lstrip('0')}.",
                )

        except ValueError as error:
            say(
                state,
                str(error),
            )

    # -----------------------------------------------------------------------
    # FREE SLOTS
    # -----------------------------------------------------------------------

    elif name == "free":
        try:
            slots = local_calendar.free_slots(
                argument
            )

            if not slots:
                say(
                    state,
                    "No free hourly slots found "
                    "between 9 AM and 6 PM.",
                )
            else:
                formatted = "\n".join(
                    datetime.strptime(
                        slot,
                        "%Y-%m-%d %H:%M",
                    ).strftime("%I:%M %p").lstrip("0")
                    for slot in slots
                )

                say(
                    state,
                    f"Free slots on {argument}:\n{formatted}",
                )

        except ValueError as error:
            say(
                state,
                str(error),
            )

    # -----------------------------------------------------------------------
    # CANCEL SINGLE EVENT — SLASH COMMAND
    # -----------------------------------------------------------------------

    elif name == "cancel-event":
        try:
            event = local_calendar.cancel_event(
                int(argument)
            )

        except (
            RuntimeError,
            ValueError,
        ) as error:
            say(
                state,
                str(error),
            )

        else:
            say(
                state,
                f"Cancelled event {event.id}: "
                f"{event.title}.",
            )

    # -----------------------------------------------------------------------
    # TASKS
    # -----------------------------------------------------------------------

    elif name == "tasks":
        say(
            state,
            list_tasks(state),
        )

    # -----------------------------------------------------------------------
    # DONE
    # -----------------------------------------------------------------------

    elif name == "done":
        try:
            index = int(argument)

            if index < 1:
                raise ValueError

            task = state.tasks[index - 1]

            task.complete = True

            store.save(state)

            say(
                state,
                f"Completed: {task.text}",
            )

        except (
            ValueError,
            IndexError,
        ):
            say(
                state,
                "Use /done followed by a valid "
                "task number from /tasks.",
            )

    # -----------------------------------------------------------------------
    # STATUS
    # -----------------------------------------------------------------------

    elif name == "status":
        open_tasks = [
            task
            for task in state.tasks
            if not task.complete
        ]

        next_task = (
            open_tasks[0].text
            if open_tasks
            else "nothing — your slate is clear"
        )

        say(
            state,
            f"{len(open_tasks)} open commitment(s), "
            f"{len(state.memories)} memory item(s). "
            f"Start with: {next_task}.",
        )

    # -----------------------------------------------------------------------
    # CLEAR CHAT
    # -----------------------------------------------------------------------

    elif name == "clear":
        state.chat.clear()

        store.save(state)

        say(
            state,
            "Local conversation history cleared. "
            "Tasks and memories are untouched.",
        )

    # -----------------------------------------------------------------------
    # LISTEN
    # -----------------------------------------------------------------------

    elif name == "listen":
        say(
            state,
            "Voice mode activated. I'm listening.",
        )

        if not voice_loop(
            state,
            store,
        ):
            return False

    # -----------------------------------------------------------------------
    # SPEAK
    # -----------------------------------------------------------------------

    elif name == "speak":
        if argument.lower() not in {
            "on",
            "off",
        }:
            say(
                state,
                "Use /speak on or /speak off.",
            )
        else:
            state.speak = (
                argument.lower() == "on"
            )

            store.save(state)

            say(
                state,
                f"Voice replies "
                f"{'enabled' if state.speak else 'disabled'}.",
            )

    # -----------------------------------------------------------------------
    # UNKNOWN COMMAND
    # -----------------------------------------------------------------------

    else:
        say(
            state,
            "Unknown command. Type /help for the list.",
        )

    return True


# ---------------------------------------------------------------------------
# NATURAL LANGUAGE CHAT + ACTION ROUTER
# ---------------------------------------------------------------------------

def chat(
    state: KevinState,
    store: StateStore,
    message: str,
) -> None:

    # -----------------------------------------------------------------------
    # TIME
    # -----------------------------------------------------------------------

    if TIME_REQUEST.match(message):
        say(
            state,
            current_time_reply(),
        )
        return

    # -----------------------------------------------------------------------
    # DATE
    # -----------------------------------------------------------------------

    date_reply = date_day_reply(message)

    if date_reply:
        say(
            state,
            date_reply,
        )
        return

    # -----------------------------------------------------------------------
    # SPOKEN CALENDAR: CREATE EVENT
    # -----------------------------------------------------------------------

    spoken_event = SPOKEN_EVENT_COMMAND.match(
        message
    )

    if spoken_event:
        title, event_date, event_time = spoken_event.groups()

        try:
            event = local_calendar.add_event(
                title,
                f"{event_date} {event_time}",
            )

        except (
            RuntimeError,
            ValueError,
        ) as error:
            say(
                state,
                str(error),
            )

        else:
            say(
                state,
                f"Added event {event.id}: "
                f"{event.title} on {event.starts_at}.",
            )

        return

    # -----------------------------------------------------------------------
    # SPOKEN CALENDAR: CHECK AVAILABILITY
    # -----------------------------------------------------------------------

    spoken_available = SPOKEN_AVAILABLE_COMMAND.match(
        message
    )

    if spoken_available:
        event_date, event_time = spoken_available.groups()

        try:
            start = local_calendar.parse_datetime(
                f"{event_date} {event_time}"
            )

            if local_calendar.is_available(start):
                say(
                    state,
                    "You're free at "
                    f"{start.strftime('%d %B %Y at %I:%M %p').lstrip('0')}.",
                )
            else:
                say(
                    state,
                    "You're already booked at "
                    f"{start.strftime('%d %B %Y at %I:%M %p').lstrip('0')}.",
                )

        except ValueError as error:
            say(
                state,
                str(error),
            )

        return

    # -----------------------------------------------------------------------
    # SPOKEN CALENDAR: FREE SLOTS
    # -----------------------------------------------------------------------

    spoken_free = SPOKEN_FREE_COMMAND.match(
        message
    )

    if spoken_free:
        event_date = spoken_free.group(1)

        try:
            slots = local_calendar.free_slots(
                event_date
            )

            if not slots:
                say(
                    state,
                    "No free hourly slots found "
                    "between 9 AM and 6 PM.",
                )
            else:
                formatted = "\n".join(
                    datetime.strptime(
                        slot,
                        "%Y-%m-%d %H:%M",
                    ).strftime("%I:%M %p").lstrip("0")
                    for slot in slots
                )

                say(
                    state,
                    f"Free slots on {event_date}:\n{formatted}",
                )

        except ValueError as error:
            say(
                state,
                str(error),
            )

        return

    # -----------------------------------------------------------------------
    # SPOKEN CALENDAR: CANCEL EVENT(S)
    # -----------------------------------------------------------------------

    spoken_cancel = SPOKEN_CANCEL_EVENT.match(
        message
    )

    if spoken_cancel:
        raw_ids = spoken_cancel.group(1).strip()

        normalized_cancel = re.sub(
            r"\s+",
            " ",
            raw_ids.lower(),
        )

        # ---------------------------------------------------------------
        # CANCEL ALL EVENTS
        # ---------------------------------------------------------------

        all_event_phrases = {
            "all",
            "all events",
            "all event",
            "everything",
            "everything on my calendar",
            "my entire calendar",
            "the entire calendar",
            "entire calendar",
            "whole calendar",
            "the whole calendar",
            "all my events",
            "all of my events",
        }

        if normalized_cancel in all_event_phrases:
            try:
                events = local_calendar.upcoming()

            except RuntimeError as error:
                say(
                    state,
                    str(error),
                )
                return

            if not events:
                say(
                    state,
                    "Your calendar is already clear.",
                )
                return

            cancelled = []
            failed = []

            # Make a copy so we don't depend on the list changing
            # while events are being removed.
            for event in list(events):
                try:
                    cancelled_event = local_calendar.cancel_event(
                        event.id
                    )

                    cancelled.append(
                        f"{cancelled_event.id}: "
                        f"{cancelled_event.title}"
                    )

                except (
                    RuntimeError,
                    ValueError,
                ):
                    failed.append(
                        f"{event.id}: {event.title}"
                    )

            # -----------------------------------------------------------
            # RESULT
            # -----------------------------------------------------------

            if cancelled and not failed:
                say(
                    state,
                    f"Cancelled all {len(cancelled)} upcoming "
                    f"event(s).",
                )

            elif cancelled and failed:
                say(
                    state,
                    f"Cancelled {len(cancelled)} event(s). "
                    f"Could not cancel {len(failed)}.",
                )

            else:
                say(
                    state,
                    "I couldn't cancel any of the upcoming events.",
                )

            return

        # ---------------------------------------------------------------
        # CANCEL SPECIFIC EVENT IDS
        # ---------------------------------------------------------------

        numbers = re.findall(
            r"\d+",
            raw_ids,
        )

        if not numbers:
            say(
                state,
                "Tell me which event numbers to cancel.",
            )
            return

        event_ids: list[int] = []

        for number in numbers:
            event_id = int(number)

            if event_id not in event_ids:
                event_ids.append(event_id)

        cancelled = []
        failed = []

        for event_id in event_ids:
            try:
                event = local_calendar.cancel_event(
                    event_id
                )

                cancelled.append(
                    f"{event.id}: {event.title}"
                )

            except (
                RuntimeError,
                ValueError,
            ):
                failed.append(
                    str(event_id)
                )

        # ---------------------------------------------------------------
        # SPECIFIC EVENT RESULT
        # ---------------------------------------------------------------

        if cancelled and not failed:

            if len(cancelled) == 1:
                say(
                    state,
                    f"Cancelled event {cancelled[0]}.",
                )
            else:
                say(
                    state,
                    "Cancelled events: "
                    + ", ".join(cancelled)
                    + ".",
                )

        elif cancelled and failed:
            say(
                state,
                "Cancelled: "
                + ", ".join(cancelled)
                + ". Could not find event(s): "
                + ", ".join(failed)
                + ".",
            )

        else:
            say(
                state,
                "I couldn't find event(s): "
                + ", ".join(failed)
                + ".",
            )

        return

    # -----------------------------------------------------------------------
    # SPOKEN CALENDAR: LIST CALENDAR
    # -----------------------------------------------------------------------

    normalized_message = (
        message.lower()
        .strip(" .?!")
    )

    if normalized_message in CALENDAR_LIST_COMMANDS:
        try:
            say(
                state,
                format_calendar(
                    local_calendar.upcoming()
                ),
            )

        except RuntimeError as error:
            say(
                state,
                str(error),
            )

        return

    # -----------------------------------------------------------------------
    # NORMAL SEARCH
    # -----------------------------------------------------------------------

    query = search_query(message)

    if query:
        try:
            browser_search(query)

        except (
            FileNotFoundError,
            OSError,
            ValueError,
        ) as error:
            say(
                state,
                f"I couldn't open Chrome: {error}",
            )

        else:
            say(
                state,
                f"Searching Google for {query}.",
            )

        return

    # -----------------------------------------------------------------------
    # AI CHAT
    # -----------------------------------------------------------------------

    ollama_model = os.getenv(
        "OLLAMA_MODEL"
    )

    api_key = os.getenv(
        "OPENAI_API_KEY"
    )

    if not ollama_model and not api_key:
        say(
            state,
            "My language model is not connected yet. "
            "Add OLLAMA_MODEL or OPENAI_API_KEY to .env, "
            "then restart me. My local commands already work — "
            "type /help.",
        )
        return

    try:
        client = (
            OllamaClient(
                ollama_model or DEFAULT_OLLAMA_MODEL
            )
            if ollama_model
            else OpenAIClient(
                api_key,
                os.getenv(
                    "KEVIN_MODEL",
                    DEFAULT_MODEL,
                ),
            )
        )

        reply = client.reply(
            message,
            state,
        )

    except KeyboardInterrupt:
        say(
            state,
            "Cancelled. I'm still here.",
        )
        return

    except RuntimeError as error:
        say(
            state,
            str(error),
        )
        return

    state.chat.extend(
        [
            {
                "role": "user",
                "content": message,
            },
            {
                "role": "assistant",
                "content": reply,
            },
        ]
    )

    store.save(state)

    say(
        state,
        reply,
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    load_env_file()

    store = StateStore()

    state = store.load()

    # KEVIN is voice-first.
    state.speak = True

    # Do not carry old model replies into a new session.
    state.chat.clear()

    store.save(state)

    print("\n" + "═" * 58)
    print(
        "  K E V I N  ·  personal command-line assistant"
    )
    print("═" * 58)

    # -----------------------------------------------------------------------
    # OWNER SETUP
    # -----------------------------------------------------------------------

    if not state.owner:
        state.owner = (
            input(
                "KEVIN: Before we begin, what's your name?\nYOU: "
            ).strip()
            or "friend"
        )

        store.save(state)

    # -----------------------------------------------------------------------
    # START VOICE MODE
    # -----------------------------------------------------------------------

    say(
        state,
        "Voice mode activated. "
        "Say 'stop listening' to use the keyboard.",
    )

    if not voice_loop(
        state,
        store,
    ):
        return

    # -----------------------------------------------------------------------
    # KEYBOARD MODE
    # -----------------------------------------------------------------------

    while True:
        try:
            raw = input(
                "YOU: "
            ).strip()

        except (
            EOFError,
            KeyboardInterrupt,
        ):
            print()

            say(
                state,
                "Standing by.",
            )

            break

        if not raw:
            continue

        typed_command = (
            raw.lower()
            .strip(" .?!")
        )

        # ---------------------------------------------------------------
        # STOP
        # ---------------------------------------------------------------

        if typed_command in APP_STOP_COMMANDS:
            say(
                state,
                "Stopping now.",
            )
            break

        # ---------------------------------------------------------------
        # START VOICE MODE
        # ---------------------------------------------------------------

        if typed_command in VOICE_START_COMMANDS:
            say(
                state,
                "Voice mode activated. I'm listening.",
            )

            if not voice_loop(
                state,
                store,
            ):
                break

            continue

        # ---------------------------------------------------------------
        # SLASH COMMAND
        # ---------------------------------------------------------------

        if raw.startswith("/"):
            if not command(
                state,
                store,
                raw,
            ):
                break

        # ---------------------------------------------------------------
        # NATURAL LANGUAGE
        # ---------------------------------------------------------------

        else:
            chat(
                state,
                store,
                raw,
            )


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()