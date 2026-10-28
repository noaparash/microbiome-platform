"""Errors meant to be shown to the user: what is wrong, and how to fix it."""

from __future__ import annotations


class UserFacingError(Exception):
    """A problem with the user's data or choice: ``.message`` says what is wrong, ``.fix`` how to fix it.

    Raised by ``analyze``, ``preprocess``, ``run_goal`` and the input readers; catch it to
    show both lines to a user. Anything else that is raised is a bug.
    """

    def __init__(self, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix
