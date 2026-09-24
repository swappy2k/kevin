import webbrowser


def open_gmail():
    """Open Gmail in the default browser."""
    webbrowser.open("https://mail.google.com")


if __name__ == "__main__":
    print("Opening Gmail...")
    open_gmail()
    from app.tools.gmail import open_gmail

open_gmail()