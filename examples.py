#!/bin/env python3

"""Usage examples for Craft CLI."""

import itertools
import logging
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import NoReturn

import craft_cli
from craft_cli import CraftError, EmitterMode, emit

USAGE = """
USAGE: examples.py <test_id> [<extra1>, [...]]")

E.g.:
    examples.py 04
    examples.py 32 brief extrastuff
"""


def example_01() -> None:
    """Show a simple message, the expected command result."""
    value = 42
    emit.message(f"The meaning of life is {value}.")


def example_02() -> None:
    """Show some progress, then the result."""
    emit.message("We need to know!")
    emit.progress("Building computer...")
    time.sleep(1.5)
    emit.progress("Asking question...")
    time.sleep(1.5)
    emit.message("The meaning of life is 42.")


def example_03() -> None:
    """Show some progress, with one long delay message, then the result."""
    emit.message("We need to know!")
    emit.progress("Building computer...")
    time.sleep(1.4)
    emit.progress("Asking question...")
    time.sleep(5)
    emit.message("The meaning of life is 42.")


def example_04() -> None:
    """Show a progress bar in brief mode."""
    emit.message("We need to know!")
    emit.progress("Deciding to build a computer or upload it...")
    time.sleep(1.5)

    with emit.progress_bar("Uploading computer: planetary model", 1788) as progress:
        for uploaded in [500, 500, 500, 288]:
            progress.advance(uploaded)
            time.sleep(1.5)

    emit.progress("Asking question...")
    time.sleep(1.5)
    emit.message("The meaning of life is 42.")


def example_05() -> None:
    """Show a verbose/debug/trace messages when it makes sense."""
    # set _mode directly to avoid the greeting and log messages that appear when using set_mode()
    for mode in EmitterMode:
        emit._mode = mode  # noqa: SLF001
        emit.verbose(f"Verbose message when mode={mode}")
    for mode in EmitterMode:
        emit._mode = mode  # noqa: SLF001
        emit.debug(f"Debug message when mode={mode}")
    for mode in EmitterMode:
        emit._mode = mode  # noqa: SLF001
        emit.trace(f"Trace message when mode={mode}")


def example_06() -> None:
    """Very long emit."""
    msg = ""
    for i in range(30):
        msg += f"progress ephemeral blah {i} "
    emit.progress(msg)

    time.sleep(5)

    msg = ""
    for i in range(30):
        msg += f"progress permanent blah {i} "
    emit.progress(msg, permanent=True)

    time.sleep(5)

    msg = ""
    for i in range(30):
        msg += f"final bleh {i} "
    emit.message(msg)


def example_07() -> None:
    """Show information that comes from a subprocess execution as a stream."""
    emit.set_mode(EmitterMode.TRACE)

    with emit.open_stream("Running ls") as stream:
        subprocess.run(["ls", "-l"], stdout=stream, stderr=stream, check=True)
    emit.message("Great!")


def example_08() -> None:
    """Show some progress that are permanent, mixed with ephemeral, then the result."""
    emit.message("We need to know!")
    emit.progress("Building computer...", permanent=True)
    time.sleep(1)
    emit.progress("Assembling stuff...")
    time.sleep(1)
    emit.progress("Asking question...", permanent=True)
    time.sleep(1)
    emit.message("The meaning of life is 42.")


def example_09() -> None:
    """Show a very simple error."""
    path = "/dev/null"
    raise CraftError(f"The file is broken; path={path!r}")


def example_10() -> None:
    """Show an error from a 3rd API, normal mode."""
    error = {"message": "Invalid channel", "code": "BAD-CHANNEL"}
    raise CraftError("Invalid channel (code 'BAD-CHANNEL')", details=repr(error))


def example_11() -> None:
    """Unexpected problem, normal mode."""
    raise ValueError("pumba")


def example_12() -> None:
    """Unexpected problem, verbose."""
    emit.set_mode(EmitterMode.TRACE)
    raise ValueError("pumba")


def example_13() -> None:
    """User cancelled."""
    emit.progress("Will hang...")
    time.sleep(120)


def example_14() -> None:
    """Support some library logging."""
    logger = logging.getLogger()
    logger.setLevel(0)

    for mode in EmitterMode:
        emit.set_mode(mode)
        emit.progress(f"Mode set to {mode}", permanent=True)
        logger.error("   some logging in ERROR")
        logger.info("   some logging in INFO")
        logger.debug("   some logging in DEBUG")
        logger.log(5, "   some logging in custom level 5")


def example_15() -> None:
    """Specific combination of long message with final message in TRACE."""
    emit.set_mode(EmitterMode.TRACE)
    emit.progress("Asking question...")
    time.sleep(3)
    emit.message("The meaning of life is 42.")


def example_16() -> None:
    """Show a progress bar, but advancing with totals."""
    emit.message("We need to know!")
    emit.progress("Deciding to build a computer or upload it...")
    time.sleep(1.5)

    with emit.progress_bar(
        "Uploading computer: planetary model", 1788, delta=False
    ) as progress:
        for uploaded in [500, 1000, 1500, 1788]:
            progress.advance(uploaded)
            time.sleep(1.5)

    emit.progress("Asking question...")
    time.sleep(1.5)
    emit.message("The meaning of life is 42.")


def example_17() -> None:
    """Raise an error chaining other."""

    def f() -> None:
        raise ValueError("pumba")

    emit.set_mode(EmitterMode.VERBOSE)
    emit.progress("Start to work", permanent=True)
    try:
        f()
    except ValueError as exc:
        raise CraftError("Exploded while working :(") from exc


def example_18() -> None:
    """Show information that comes from a subprocess execution as a stream."""
    emit.set_mode(EmitterMode.TRACE)

    with emit.open_stream(
        "Running a two parts something that will take time"
    ) as stream:
        cmd = ["bash", "-c", "sleep 5 && echo Part 1 && sleep 5 && echo Part 2"]
        subprocess.run(cmd, stdout=stream, stderr=stream, check=True)
    emit.message("All done.")


def example_19() -> None:
    """Support some deep inside library logging."""
    emit.set_mode(EmitterMode.TRACE)

    logger = logging.getLogger("foobar.__main__")
    logger.setLevel(logging.DEBUG)
    logger.debug("Some logging in DEBUG")


def example_20() -> None:
    """Show information that comes from a subprocess execution as a stream, Windows version."""
    emit.set_mode(EmitterMode.TRACE)

    with emit.open_stream("Running a simple Windows command") as stream:
        subprocess.run(
            ["python.exe", "-V"], stdout=stream, stderr=subprocess.STDOUT, check=True
        )
    emit.message("Great!")


def _run_subprocess_with_emitter(mode: EmitterMode) -> None:
    """Write a temp app that uses emitter and run it."""
    emit.set_mode(mode)

    example_test_sub_app = textwrap.dedent(
        """
        import sys
        import time

        from craft_cli import emit, EmitterMode

        mode = EmitterMode[sys.argv[1]]

        emit.init(mode, "subapp", "An example sub application.")
        emit.progress("Sub app: starting")
        time.sleep(6)
        emit.progress("Sub app: Lot of work")
        time.sleep(6)
        emit.message("Sub app: Done")
        emit.ended_ok()
    """
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf8") as file:
        file.write(example_test_sub_app)
        emit.progress("We're about to test a sub app")
        time.sleep(3)
        with emit.pause():
            subprocess.run(
                [sys.executable, file.name, mode.name],
                env={"PYTHONPATH": Path.cwd()},
                check=True,
            )
            # note we cannot use `emit` while paused!
    emit.message("All done!")


def example_21() -> None:
    """Run an app that uses emitter in a subprocess, pausing the external control, brief mode."""
    _run_subprocess_with_emitter(EmitterMode.BRIEF)


def example_22() -> None:
    """Run an app that uses emitter in a subprocess, pausing the external control, trace mode."""
    _run_subprocess_with_emitter(EmitterMode.TRACE)


def example_23() -> None:
    """Capture output from an app that uses emitter."""
    emit.set_mode(EmitterMode.TRACE)

    example_test_sub_app = textwrap.dedent(
        """
        import time

        from craft_cli import emit, EmitterMode

        emit.init(EmitterMode.BRIEF, "subapp", "An example sub application.")
        emit.progress("Sub app: starting")
        time.sleep(6)
        emit.progress("Sub app: Lot of work")
        time.sleep(1)
        emit.message("Sub app: Done")
        emit.ended_ok()
    """
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf8") as file:
        file.write(example_test_sub_app)
        emit.progress("Running subprocess...")
        cmd = [sys.executable, file.name]
        proc = subprocess.run(
            cmd,
            env={"PYTHONPATH": Path.cwd()},
            capture_output=True,
            text=True,
            check=True,
        )
    emit.message("Captured output:")
    for line in filter(
        None, itertools.chain(proc.stderr.split("\n"), proc.stdout.split("\n"))
    ):
        emit.message(f":: {line}")


def example_24() -> None:
    """Show a progress bar in verbose mode."""
    emit.set_mode(EmitterMode.VERBOSE)

    emit.progress("We need to know!", permanent=True)
    emit.progress("Deciding to build a computer or upload it...")
    time.sleep(1.5)

    with emit.progress_bar("Uploading computer: planetary model", 1788) as progress:
        for uploaded in [500, 500, 500, 288]:
            progress.advance(uploaded)
            time.sleep(1.5)

    emit.progress("Asking question...")
    time.sleep(1.5)
    emit.message("The meaning of life is 42.")


def example_25() -> None:
    """Show a progress bar in debug mode."""
    emit.set_mode(EmitterMode.DEBUG)

    emit.progress("We need to know!", permanent=True)
    emit.progress("Deciding to build a computer or upload it...")
    time.sleep(1.5)

    with emit.progress_bar("Uploading computer: planetary model", 1788) as progress:
        for uploaded in [500, 500, 500, 288]:
            progress.advance(uploaded)
            time.sleep(1.5)

    emit.progress("Asking question...")
    time.sleep(1.5)
    emit.message("The meaning of life is 42.")


def example_26() -> None:
    """Show emitter progress message handover.

    This example demonstrates seamless emitter progress message handover
    between two craft tools. Handover uses emit.pause() on the local
    craft tool before an LXD launched craft tool takes over, and hands back.
    """
    emit.set_mode(EmitterMode.BRIEF)

    lxd_craft_tool = textwrap.dedent(
        """
        import time

        from craft_cli import emit, EmitterMode

        emit.init(EmitterMode.BRIEF, "subapp", "An example sub application.")
        emit.progress("seamless progress #2")
        time.sleep(2)
        emit.progress("seamless progress #3")
        time.sleep(2)
        emit.ended_ok()
    """
    )
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf8") as file:
        file.write(lxd_craft_tool)

        emit.message("Application Start.")
        emit.progress("seamless progress #1")
        time.sleep(2)
        with emit.pause():
            cmd = [sys.executable, file.name]
            subprocess.run(
                cmd,
                env={"PYTHONPATH": Path.cwd()},
                capture_output=False,
                text=True,
                check=True,
            )
    emit.progress("seamless progress #4")
    time.sleep(2)
    emit.message("Application End.")


def _run_noisy_subprocess(
    mode_name: str, total_messages: int, subprocess_code: str
) -> None:
    """Capture the output of a noisy subprocess in different modes."""
    mode = EmitterMode[mode_name.upper()]
    emit.set_mode(mode)

    with tempfile.NamedTemporaryFile("w", encoding="utf8") as file:
        file.write(subprocess_code)
        emit.progress("About to run a noisy subprocess")
        time.sleep(1)
        with emit.open_stream("Running custom Python app in unbuffered mode") as stream:
            cmd = [sys.executable, "-u", file.name, str(total_messages)]
            subprocess.check_call(cmd, stdout=stream, stderr=stream)

    emit.message("All done!")


def example_27(mode_name: str, total_messages: int = 10) -> None:
    """Capture the output of a noisy subprocess in different modes."""
    example_test_sub_app = textwrap.dedent(
        """
        import sys
        import time
        from random import random, randint, sample
        from string import ascii_lowercase as letters

        total = int(sys.argv[1])
        for idx in range(total):
            short = random() > .2
            delay = random() / 4 if short else random() * 2
            delay_for_spinner = random() > .9
            more = " ".join("".join(sample(letters, randint(3, 8))) for _ in range(randint(5, 30)))
            print(f"Noisy message {idx} / {total} -- {more}", flush=True)
            time.sleep(delay)
            if delay_for_spinner:
                time.sleep(5)
    """
    )
    _run_noisy_subprocess(mode_name, total_messages, example_test_sub_app)


def example_28(mode_name: str, total_messages: int = 10) -> None:
    """Capture the multi-line, tab-containing output of a noisy subprocess."""
    example_test_sub_app = textwrap.dedent(
        """
        import sys
        import time
        import textwrap

        total = int(sys.argv[1])
        for idx in range(total):
            #short = random() > .2
            delay = 1
            delay_for_spinner = False # random() > .9
            message = textwrap.dedent(f'''
            This first message should never appear.
            \tThis second message shouldn't appear either.
            \tThis line should appear, preceded "::   " ({idx} / {total}).
            ''').strip()
            print(message,flush=True)
            time.sleep(delay)
            if delay_for_spinner:
                time.sleep(5)
    """
    )
    _run_noisy_subprocess(mode_name, total_messages, example_test_sub_app)


def example_29(
    mode_name: str,
    streaming_brief: bool = False,  # noqa: FBT001, FBT002
) -> None:
    """Support some library logging."""
    logger = logging.getLogger()
    logger.setLevel(0)

    mode = EmitterMode[mode_name.upper()]
    emit.init(mode, "example_29", "Hi", streaming_brief=streaming_brief)

    emit.progress(f"Mode set to {mode}", permanent=True)

    emit.progress("Starting up lib1", permanent=False)
    _call_lib(logger, 1)
    emit.progress("Finished lib1", permanent=True)

    emit.progress("Starting up lib2", permanent=False)
    _call_lib(logger, 2)
    emit.progress("Finished lib2", permanent=True)

    emit.progress("Starting up lib3", permanent=False)
    _call_lib(logger, 3)
    emit.progress("Finished lib3", permanent=True)


def _call_lib(logger: logging.Logger, index: int) -> None:
    lib = f"lib{index}"

    time.sleep(2)
    logger.info(f"   {lib} INFO 1")
    logger.debug(f"   {lib} DEBUG 1")
    time.sleep(2)
    logger.info(f"   {lib} INFO 2")
    logger.debug(f"   {lib} DEBUG 2")
    time.sleep(2)


def example_30() -> None:
    """Message spamming, noting the different spinner behaviour."""
    emit.progress(
        "Message spamming example. The same message will be spammed for 10s, but "
        "it will appear as one message with a spinner.",
        permanent=True,
    )
    end_time = time.monotonic() + 10
    while time.monotonic() < end_time:
        emit.progress("SPAM SPAM SPAM SPAM")
        time.sleep(0.001)
    emit.progress(
        "Now two separate messages will be spammed and no spinner appear.",
        permanent=True,
    )
    end_time = time.monotonic() + 10
    while time.monotonic() < end_time:
        emit.progress("SPAM SPAM SPAM SPAM")
        time.sleep(0.01)
        emit.progress("SPAM SPAM SPAM baked beans")
        time.sleep(0.01)
    emit.progress("And back to the first message!", permanent=True)
    end_time = time.monotonic() + 10
    while time.monotonic() < end_time:
        emit.progress("SPAM SPAM SPAM SPAM")
        time.sleep(0.001)


def example_31() -> None:
    """Multiline error message."""
    emit.progress("Setting up computer for build...")
    time.sleep(1)
    emit.progress("A long progress message")
    time.sleep(6)
    raise CraftError("Error 1\nError 2")


def example_32() -> NoReturn:
    """Showcase the cursor being restored even after an uncaught exception."""
    emit.progress("Look ma, no cursor!")
    raise BaseException  # noqa: TRY002


def example_33() -> None:
    """Showcase error reporting."""
    error = craft_cli.CraftError(
        message="Something unexpected happened.",
        details="These are error details.",
        logpath_report=False,
    )
    emit.error(error)


def example_34() -> None:
    """Showcase error reporting (details with multiple lines)."""
    error = craft_cli.CraftError(
        message="Something unexpected happened.",
        details="These are error details.\n- A new line\n- Another line",
        logpath_report=False,
    )
    emit.error(error)


def example_35() -> None:
    """Showcase warnings among both ephemeral and permanent progress messages."""
    emit.message("Hello and welcome to earth!")
    emit.message("Please wait while we take over.")
    time.sleep(1)

    emit.progress("Initializing global domination protocol...", permanent=True)
    time.sleep(2)

    emit.progress("Depleting coffee supply...", permanent=False)
    time.sleep(2)
    emit.warning("Human resistance detected... deploying cat videos.")
    time.sleep(2)
    emit.progress("Coffee supply successfully depleted.", permanent=True)
    time.sleep(0.5)

    emit.progress("Removing cat videos...", permanent=True)
    time.sleep(2)
    emit.warning("Cat resistance detected... deploying humans.", prefix="CRITICAL: ")
    time.sleep(2)
    emit.progress("Cat videos successfully removed.", permanent=True)

    emit.message("Takeover complete. Have a nice day!")


# -- end of test cases

if len(sys.argv) < 2:  # noqa: PLR2004, magic value
    print(USAGE)
    sys.exit()

name = f"example_{int(sys.argv[1]):02d}"
func = globals().get(name)
if func is None:
    print(f"ERROR: function {name!r} not found")
    sys.exit()

if int(sys.argv[1]) != 29:  # noqa: PLR2004, magic value
    emit.init(EmitterMode.BRIEF, "examples", "Greetings earthlings")
try:
    func(*sys.argv[2:])
except CraftError as err:
    emit.error(err)
except KeyboardInterrupt as exc:
    msg = "User cancelled"
    error = CraftError(msg)
    error.__cause__ = exc
    emit.error(error)
except Exception as exc:  # noqa: BLE001, blind exception, fine since these are examples
    msg = f"Unexpected internal exception: {exc!r}"
    error = CraftError(msg)
    error.__cause__ = exc
    emit.error(error)
else:
    emit.ended_ok()
