from enum import Enum
from pathlib import Path

from craft_cli._rs.progress import Progresser

from .streams import StreamHandle

class Verbosity(Enum):
    """Verbosity modes."""

    QUIET = ...
    """Quiet output. Most messages should not be output at all."""

    BRIEF = ...
    """Brief output. Most messages should be ephemeral and all debugging
    message types should be skipped."""

    VERBOSE = ...
    """Verbose mode. All messages should be persistent and some debugging
    message types are output."""

    DEBUG = ...
    """Debug mode. Almost all messages are printed and persistent, except
    for highly verbose messages from external libraries."""

    TRACE = ...
    """Trace mode. Absolutely all messages are printed and persistent."""

class Emitter:
    """The Emitter is the primary entry point of Craft CLI for message printing and logging.

    The act of "emitting", in the context of the Emitter, is the handling of a given
    message event. For a given message, depending on the verbosity level and the
    sort of message sent, this could mean as little as simply sending it to the log
    file. It could also mean as much as finishing up a spinning "in-progress"
    action, rendering its time elapsed over that line, prepending a timestamp to the
    new message, and sending it to both the terminal and the log file.
    """

    def __init__(
        self,
        verbosity: Verbosity,
        log_filepath: str,
        greeting: str,
        *,
        docs_base_url: str | None = None,
        streaming_brief: bool = False,
    ) -> None:
        """Construct a new ``Emitter`` from Python.

        The supplied ``greeting`` is emitted upon instantiation. ``docs_base_url`` is
        used as a prefix for documentation slugs supplied by certain error types.

        ## Streaming Brief

        If ``Verbosity.BRIEF`` is set, "streaming brief" mode is used to provide extra
        information without flooding the terminal session. Otherwise excessively verbose
        messages will be emitted ephemerally, being overwritten by the next message.

        This is often a good default for applications, as it gives feedback about progress
        without inundating a user with excessive information.
        """

    @classmethod
    def log_filepath_from_name(cls, app_name: str) -> Path:
        """Create a log filepath from an app name as an easy default."""

    def get_verbosity(self) -> Verbosity:
        """Get the current verbosity level."""

    def set_verbosity(self, new: Verbosity) -> None:
        """Set the verbosity level."""

    def verbose(self, text: str) -> None:
        """Send a verbose message.

        Useful for providing more information to the user that isn't particularly
        helpful for "regular use".
        """

    def debug(self, text: str) -> None:
        """Send a debug message.

        Use to record anything that the user may not want to normally see, but
        would be useful for the app developers to understand why things may be
        failing.
        """

    def trace(self, text: str) -> None:
        """Send a trace message.

        Use to expose system-generated information which in general would be
        overwhelming for debugging purposes but sometimes needed for more
        in-depth analysis.
        """

    def progress(self, text: str, *, permanent: bool = False) -> None:
        """Send a progress message.

        This is normally used to present several related messages relaying how
        a task is going.

        These messages will be overwritten by the next line. If a progress message
        is important enough that it shouldn't be overwritten by the next ones, set
        ``permanent`` to ``true``.
        """

    def message(self, text: str) -> None:
        """Send a message.

        Ideally used as the final message in a sequence to show a result, as it
        goes to stdout unlike other message types.
        """

    def warning(self, text: str, *, prefix: str = "WARNING: ") -> None:
        """Show a warning message.

        By default, messages will be prefixed with "WARNING: ". An alternative prefix
        can be provided via the ``prefix`` parameter.
        """

    def ended_ok(self) -> None:
        """Stop gracefully."""

    def open_stream(self, prefix: str | None) -> StreamHandle:
        """Open a stream context manager to redirect output to a different stream.

        If a prefix is provided, each message received through this handle will be
        prefixed with that string.
        """

    def set_prefix(self, prefix: str) -> None:
        """Set a prefix for each message."""

    def clear_prefix(self) -> None:
        """Clear the current prefix."""

    def progress_bar(
        self,
        text: str,
        total: int,
        *,
        units: str | None = None,
        show_eta: bool = False,
        show_progress: bool = False,
        show_percentage: bool = False,
    ) -> Progresser:
        """Render an incremental progress bar.

        This method must be used as a context manager.

        :param text: A brief message to prefix before the progress bar.
        :param total: The total size of the progress bar. Must be a positive number.
        :param units: Units to display to the left of the progress bar, like "X/Y
            units". Implies `show_progress = True`. If set to None, the total count will
            not be showed at all. If set to "bytes", the total will automatically be
            adjusted to an appropriate magnitude (e.g., MiB -> GiB). All other values are
            used as-is. Defaults to None.
        :param show_eta: Whether or not to display an estimated ETA to the right of the
            progress bar.
        :param show_progress: Whether or not to show progress to the right of the progress
            bar, like "X/Y".
        :param show_percentage: Whether or not to display a percentage of completion to the
            right of the progress bar.

        :return: A Progresser context manager.
        """
