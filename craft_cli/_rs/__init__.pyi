import logging

class LogListener:
    """A handler for log records from Python's ``logging`` library.

    Integrates with Craft CLI's Emitter.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Handle a log record."""
