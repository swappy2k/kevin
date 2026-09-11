from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


CALENDAR_FILE = Path(__file__).resolve().parents[2] / "calendar.json"


@dataclass
class CalendarEvent:
    id: int
    title: str
    starts_at: datetime


class Calendar:
    def __init__(self):
        self.events: list[CalendarEvent] = []
        self.load()

    def load(self):
        if not CALENDAR_FILE.exists():
            self.events = []
            self.save()
            return

        try:
            raw = json.loads(
                CALENDAR_FILE.read_text(encoding="utf-8")
            )

            self.events = [
                CalendarEvent(
                    id=item["id"],
                    title=item["title"],
                    starts_at=datetime.fromisoformat(
                        item["starts_at"]
                    ),
                )
                for item in raw
            ]

        except (
            json.JSONDecodeError,
            KeyError,
            ValueError,
            TypeError,
        ):
            self.events = []

    def save(self):
        data = [
            {
                "id": event.id,
                "title": event.title,
                "starts_at": event.starts_at.isoformat(),
            }
            for event in self.events
        ]

        CALENDAR_FILE.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )

    # -------------------------
    # EVENT / BOOKING
    # -------------------------

    def add_event(
        self,
        title: str,
        starts_at: str,
    ) -> CalendarEvent:

        title = title.strip()
        starts_at = starts_at.strip()

        if not title:
            raise ValueError(
                "Event title cannot be empty."
            )

        start = self.parse_datetime(starts_at)

        if not self.is_available(start):
            raise ValueError(
                f"That time is already booked."
            )

        next_id = max(
            (event.id for event in self.events),
            default=0,
        ) + 1

        event = CalendarEvent(
            id=next_id,
            title=title,
            starts_at=start,
        )

        self.events.append(event)

        self.events.sort(
            key=lambda item: item.starts_at
        )

        self.save()

        return event

    def cancel_event(
        self,
        event_id: int,
    ) -> CalendarEvent:

        for index, event in enumerate(self.events):
            if event.id == event_id:
                removed = self.events.pop(index)
                self.save()
                return removed

        raise ValueError(
            f"No calendar event found with ID {event_id}."
        )

    # -------------------------
    # AVAILABILITY
    # -------------------------

    def is_available(
        self,
        starts_at: datetime,
    ) -> bool:

        for event in self.events:
            if event.starts_at == starts_at:
                return False

        return True

    def check_availability(
        self,
        starts_at: str,
    ) -> bool:

        start = self.parse_datetime(starts_at)

        return self.is_available(start)

    # -------------------------
    # UPCOMING
    # -------------------------

    def upcoming(self) -> list[CalendarEvent]:

        now = datetime.now()

        return [
            event
            for event in self.events
            if event.starts_at >= now
        ]

    def today(self) -> list[CalendarEvent]:

        today = datetime.now().date()

        return [
            event
            for event in self.events
            if event.starts_at.date() == today
        ]

    # -------------------------
    # DATE / TIME
    # -------------------------

    @staticmethod
    def parse_datetime(
        value: str,
    ) -> datetime:

        try:
            return datetime.strptime(
                value,
                "%Y-%m-%d %H:%M",
            )

        except ValueError as error:
            raise ValueError(
                "Use date/time format "
                "YYYY-MM-DD HH:MM."
            ) from error

    @staticmethod
    def now() -> datetime:
        return datetime.now()

    @staticmethod
    def tomorrow() -> datetime:
        return datetime.now() + timedelta(days=1)

    # -------------------------
    # FREE SLOTS
    # -------------------------

    def free_slots(
        self,
        date_value: str,
        start_hour: int = 9,
        end_hour: int = 18,
    ) -> list[str]:

        try:
            day = datetime.strptime(
                date_value,
                "%Y-%m-%d",
            ).date()

        except ValueError as error:
            raise ValueError(
                "Use date format YYYY-MM-DD."
            ) from error

        free = []

        for hour in range(
            start_hour,
            end_hour,
        ):
            slot = datetime(
                day.year,
                day.month,
                day.day,
                hour,
                0,
            )

            if self.is_available(slot):
                free.append(
                    slot.strftime("%Y-%m-%d %H:%M")
                )

        return free


calendar = Calendar()