# Copyright 2026 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""Integration with the logging library."""

import logging
from typing import Any

from typing_extensions import override

from ._rs import LogListener


class LogHandler(logging.Handler):
    """Integrate with the logging library.

    This class wraps a Rust implementation with the required `emit` method.
    """

    @override
    def __init__(self, inner_handler: LogListener, **kwargs: dict[str, Any]) -> None:
        super().__init__(*kwargs)
        # Always log at level 0 so that we see _all_ log messages
        self.level = 0
        self.inner_handler = inner_handler

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.inner_handler.emit(record)


def setup_logging_capture(log_listener: LogListener) -> LogHandler:
    log_handler = LogHandler(log_listener)
    root_logger = logging.getLogger()
    root_logger.setLevel(0)
    root_logger.addHandler(log_handler)
    return log_handler
