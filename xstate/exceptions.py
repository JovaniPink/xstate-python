"""xstate-specific exception hierarchy."""


class XStateError(Exception):
    """Base class for all xstate errors."""


class InvalidConfigError(XStateError):
    """Raised when a machine configuration is invalid."""


class UnregisteredImplementationError(XStateError):
    """Raised when a named guard, action, or delay has no registered implementation."""
