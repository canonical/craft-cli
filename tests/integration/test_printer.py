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

"""Integration tests for printer behavior."""

import shutil
import subprocess
import sys
import textwrap

import pytest


def test_captured_stdout_broken_pipe_does_not_fail_at_shutdown():
    """A closed stdout pipe should not fail during interpreter shutdown."""
    head = shutil.which("head")
    if head is None:
        pytest.skip("'head' command is required for this regression test")

    script = textwrap.dedent(
        """
        import pathlib
        import sys
        import tempfile
        import time

        import craft_cli.printer as printer_module
        from craft_cli.printer import Printer

        printer_module.TESTMODE = True

        with tempfile.TemporaryDirectory() as tmp:
            printer = Printer(pathlib.Path(tmp) / "craft-cli.log")

            sys.stdout.write("first\\n")
            sys.stdout.flush()

            time.sleep(0.2)

            printer.show(sys.stdout, "buffered-after-consumer-closed")
        """
    )

    producer = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert producer.stdout is not None
    assert producer.stderr is not None

    consumer = subprocess.Popen(
        [head, "-n", "1"],
        stdin=producer.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    producer.stdout.close()

    consumer_stdout, consumer_stderr = consumer.communicate()
    producer_stderr = producer.stderr.read()
    producer_status = producer.wait()

    assert consumer.returncode == 0
    assert consumer_stdout == "first\n"
    assert consumer_stderr == ""

    assert producer_status == 0
    assert "BrokenPipeError" not in producer_stderr
