"""Open Google searches in the user's normal Google Chrome profile."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from urllib.parse import quote_plus


GOOGLE_SEARCH = "https://www.google.com/search?q={}"
CHROME_LOCATIONS = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
)


def search(query: str) -> str:
    """Open *query* in the user's normal Chrome profile and return the URL.

    If Chrome is already running, Chrome opens the search as another tab in that
    existing personal session. If it is closed, it starts with the same profile.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("A search query is required.")

    chrome = _find_chrome()
    search_url = GOOGLE_SEARCH.format(quote_plus(cleaned_query))
    subprocess.Popen(
        [str(chrome), "--profile-directory=Default", "--new-tab", search_url],
        close_fds=True,
    )
    return search_url


def _find_chrome() -> Path:
    """Return the installed Chrome executable or explain what is missing."""
    for location in CHROME_LOCATIONS:
        if location.is_file():
            return location
    raise FileNotFoundError(
        "Google Chrome was not found. Install Chrome or add its location to "
        "CHROME_LOCATIONS in app/tools/browser.py."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Search Google in normal Chrome.")
    parser.add_argument("query", nargs="+", help="Words to search for")
    args = parser.parse_args()
    search_url = search(" ".join(args.query))
    print(f"Opened in your normal Chrome profile: {search_url}")


if __name__ == "__main__":
    main()
