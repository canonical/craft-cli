import logging

class LogListener:
    def emit(self, record: logging.LogRecord) -> None: ...
