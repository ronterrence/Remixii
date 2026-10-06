class RemixiiError(Exception):
    """Base class for user-facing application errors."""


class MediaError(RemixiiError):
    """The supplied media could not be read or processed."""


class PackageError(RemixiiError):
    """A .remix project is invalid or unsafe."""


class GenerationError(RemixiiError):
    """The configured generation service failed."""

