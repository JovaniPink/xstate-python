__all__ = ["XStateError", "InvalidConfigError", "UnregisteredImplementationError"]


class XStateError(Exception):
    """Base class for all xstate errors."""


class InvalidConfigError(XStateError, ValueError):
    """Raised when a machine configuration is invalid.

    Subclasses :class:`ValueError` for backwards compatibility with callers that
    already catch ``ValueError`` on bad machine configurations.
    """


class UnregisteredImplementationError(XStateError, UserWarning, ValueError):
    """Raised or warned when a named implementation is missing.

    Subclasses :class:`XStateError` and :class:`UserWarning` so it can be
    used as either a ``raise`` target or a ``warnings.warn`` category.
    Subclasses :class:`ValueError` for backwards compatibility with callers
    that catch ``ValueError`` around guard or delay resolution.
    """
