"""Shared error type for rule violations."""


class TaskError(ValueError):
    """Raised when an action breaks a rule (missing reason, locked period, ...)."""
