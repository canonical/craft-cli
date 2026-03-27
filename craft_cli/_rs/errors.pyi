"""Base error type supported by an Emitter."""

class CraftError(Exception):
    """A program error to report with context."""

    message: str
    """The main message to the user, to be shown as the first line of the error."""

    details: str | None
    """Deeper, verbose error details that may help with diagnosing the deeper issue."""

    resolution: str | None
    """A brief suggestion for how the user might resolve the error themselves."""

    docs_url: str | None
    """A URL to point the user towards for troubleshooting.

    Supersedes `docs_slug`."""

    docs_slug: str | None
    """A slug to append to user documentation.

    This field is meant to be appended to a base URL provided by the method handling this error.

    Is superseded by `docs_url`."""

    show_logpath: bool
    """Whether to display the path to the log alongside this message.

    It is generally recommended to leave this on, but some extremely simple error cases may
    display better without the log path."""

    retcode: int
    """The code to return when the application finishes.

    This error class does not exit the program itself. Instead, this field is meant to be used
    by a consumer inspecting the error message."""

    def __init__(
        self,
        message: str,
        *,
        details: str | None = None,
        resolution: str | None = None,
        docs_url: str | None = None,
        docs_slug: str | None = None,
        show_logpath: bool = True,
        retcode: int = 1,
    ) -> None: ...
