# Copyright 2023 Canonical Ltd.
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

import logging
import multiprocessing
import sys
from textwrap import dedent

from craft_cli import emit, EmitterMode

logger = logging.getLogger()


def strip_timestamps(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(line.split(" ", maxsplit=2)[-1])
    return "\n".join(lines)


def child_func():
    logger.info("Message 1 from CHILD process")
    logger.info("Message 2 from CHILD process")


def test_logging_in_multiprocess(tmp_path):
    """Test the behavior of the logging integration with multiprocessing parallelism."""
    logger.setLevel(logging.INFO)
    emitter_log = tmp_path / "emitter_log.txt"
    greeting = "hi"
    emit.init(
        mode=EmitterMode.QUIET, appname="testapp", greeting=greeting, log_filepath=emitter_log
    )

    logger.info("Message 1 from PARENT process")
    logger.info("Message 2 from PARENT process")

    child = multiprocessing.Process(target=child_func)
    child.start()
    child.join()

    logger.info("Message 3 from PARENT process")

    emit.ended_ok()

    emitter_logged = strip_timestamps(emitter_log.read_text())

    if sys.platform == "linux":
        # Expect two messages from the parent process, then two from the child process,
        # then a final one from the parent again.
        expected_text = dedent(
            """\
            Message 1 from PARENT process
            Message 2 from PARENT process
            Message 1 from CHILD process
            Message 2 from CHILD process
            Message 3 from PARENT process
            """
        )
    else:
        # Messages from the child process are NOT logged in non-Linux platforms. This
        # is not by design, but a record of the current expected behavior.
        expected_text = dedent(
            """\
            Message 1 from PARENT process
            Message 2 from PARENT process
            Message 3 from PARENT process
            """
        )

    assert emitter_logged == f"{greeting}\n" + expected_text.rstrip()
