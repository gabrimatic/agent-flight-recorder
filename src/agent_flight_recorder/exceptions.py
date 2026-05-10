class AFRError(Exception):
    """Base user-facing Agent Flight Recorder error."""


class GitError(AFRError):
    """Raised when git cannot provide required repository information."""


class ConfigError(AFRError):
    """Raised when project configuration is invalid."""


class SessionError(AFRError):
    """Raised when a session cannot be created, loaded, or stopped."""
