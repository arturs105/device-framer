"""Shared user-facing plumbing: program name, errors, warnings, TTY checks."""

from __future__ import annotations

import sys

PROG = "device-framer"
USER_AGENT = f"{PROG}/0.1"


class CliError(Exception):
    """A user-facing error; the message is printed and the exit code is 1."""


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
