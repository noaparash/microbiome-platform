"""Errors meant to be shown to the user: what is wrong, and how to fix it."""

from __future__ import annotations


class UserFacingError(Exception):
    def __init__(self, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix
