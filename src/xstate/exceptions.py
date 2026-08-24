__all__ = [
    "XStateError",
    "InvalidConfigError",
    "InfiniteLoopError",
    "UnregisteredImplementationError",
]


class XStateError(Exception):
    """Base class for all xstate errors."""


class InvalidConfigError(XStateError, ValueError):
    """Raised when a machine configuration is invalid.

    Subclasses :class:`ValueError` for backwards compatibility with callers that
    already catch ``ValueError`` on bad machine configurations.
    """


class InfiniteLoopError(XStateError):
    """Raised before a macrostep exceeds its configured iteration limit."""

    def __init__(self, machine_id: str, limit: int, event_type: str):
        super().__init__(
            f"Machine '{machine_id}' exceeded max iterations {limit} for event "
            f"'{event_type}'."
        )


class UnregisteredImplementationError(XStateError, UserWarning, ValueError):
    """Raised or warned when a named implementation is missing.

    Subclasses :class:`XStateError` and :class:`UserWarning` so it can be
    used as either a ``raise`` target or a ``warnings.warn`` category.
    Subclasses :class:`ValueError` for backwards compatibility with callers
    that catch ``ValueError`` around guard or delay resolution.
    """
