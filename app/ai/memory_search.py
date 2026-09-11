"""
KEVIN — Memory Search

Simple local memory retrieval for KEVIN.
No external database required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass
class MemoryMatch:
    text: str
    score: int


def _words(text: str) -> set[str]:
    """Convert text into useful lowercase words."""
    return {
        word
        for word in re.findall(r"[a-zA-Z0-9']+", text.lower())
        if len(word) > 1
    }


def score_memory(query: str, memory: str) -> int:
    """
    Score how relevant a memory is to a query.

    Higher score = stronger match.
    """
    query_words = _words(query)
    memory_words = _words(memory)

    if not query_words or not memory_words:
        return 0

    score = len(query_words & memory_words)

    # Small bonus when the exact query appears.
    if query.lower().strip() in memory.lower():
        score += 3

    return score


def search_memories(
    query: str,
    memories: Iterable[str],
    limit: int = 5,
) -> list[MemoryMatch]:
    """
    Search through local memories and return the most relevant ones.
    """

    matches: list[MemoryMatch] = []

    for memory in memories:
        if not memory:
            continue

        score = score_memory(query, memory)

        if score > 0:
            matches.append(
                MemoryMatch(
                    text=memory,
                    score=score,
                )
            )

    matches.sort(key=lambda match: match.score, reverse=True)

    return matches[:limit]


def format_memory_context(
    query: str,
    memories: Iterable[str],
    limit: int = 5,
) -> str:
    """
    Convert relevant memories into text that can be given to KEVIN's brain.
    """

    matches = search_memories(
        query=query,
        memories=memories,
        limit=limit,
    )

    if not matches:
        return ""

    lines = [
        f"- {match.text}"
        for match in matches
    ]

    return "\n".join(lines)