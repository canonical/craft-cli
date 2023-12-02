#!/bin/env python3

import itertools
import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import time

from craft_cli import CraftError, EmitterMode, emit

USAGE = """
USAGE: explorator.py <test_id> [<extra1>, [...]]")

E.g.:
    explorator.py 04
    explorator.py 32 brief extrastuff
"""


def example_01():
    """Show a simple message, the expected command result."""
    value = 42
    emit.message(f"The meaning of life is {value}.")


def example_02():
    """Show some progress, then the result."""
    emit.message("We need to know!")
    emit.progress("Building computer...")
    time.sleep(1.5)
    emit.progress("Asking question...")
    time.sleep(1.5)
    emit.message("The meaning of life is 42.")


def example_03():
    """Show some progress, with one long delay message, then the result."""
    emit.message("We need to know!")
    emit.progress("Building computer...")
    time.sleep(1.4)
    emit.progress("Asking question...")
    time.sleep(5)
    emit.message("The meaning of life is 42.")


def example_04():
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


def example_05():
    """Show a verbose/debug/trace messages when it makes sense."""
    # set _mode directly to avoid the greeting and log messages that appear when using set_mode()
    for mode in EmitterMode:
        emit._mode = mode
        emit.verbose(f"Verbose message when mode={mode}")
    for mode in EmitterMode:
        emit._mode = mode
        emit.debug(f"Debug message when mode={mode}")
    for mode in EmitterMode:
        emit._mode = mode
        emit.trace(f"Trace message when mode={mode}")


def example_06():
    """Very long emit."""
    msg = ""
    for i in range(30):
        msg += "progress ephemeral blah {} ".format(i)
    emit.progress(msg)

    time.sleep(5)

    msg = ""
    for i in range(30):
        msg += "progress permanent blah {} ".format(i)
    emit.progress(msg, permanent=True)

    time.sleep(5)

    msg = ""
    for i in range(30):
        msg += "final bleh {} ".format(i)
    emit.message(msg)


def example_07():
    """Show information that comes from a subprocess execution as a stream."""
    emit.set_mode(EmitterMode.TRACE)

    with emit.open_stream("Running ls") as stream:
        subprocess.run(["ls", "-l"], stdout=stream, stderr=stream)
    emit.message("Great!")


def example_08():
    """Show some progress that are permanent, mixed with ephemeral, then the result."""
    emit.message("We need to know!")
    emit.progress("Building computer...", permanent=True)
    time.sleep(1)
    emit.progress("Assembling stuff...")
    time.sleep(1)
    emit.progress("Asking question...", permanent=True)
    time.sleep(1)
    emit.message("The meaning of life is 42.")


def example_09():
    """Show a very simple error."""
    path = "/dev/null"
    raise CraftError(f"The file is broken; path={path!r}")


def example_10():
    """An error from a 3rd API, normal mode."""
    # emit.set_mode(EmitterMode.TRACE)
    error = {"message": "Invalid channel", "code": "BAD-CHANNEL"}
    raise CraftError("Invalid channel (code 'BAD-CHANNEL')", details=repr(error))


def example_11():
    """Unexpected problem, normal mode."""
    raise ValueError("pumba")


def example_12():
    """Unexpected problem, verbose."""
    emit.set_mode(EmitterMode.TRACE)
    raise ValueError("pumba")


def example_13():
    """User cancelled."""
    # emit.set_mode(EmitterMode.TRACE)
    emit.progress("Will hang...")
    time.sleep(120)


def example_14():
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


def example_15():
    """Specific combination of long message with final message in TRACE."""
    emit.set_mode(EmitterMode.TRACE)
    emit.progress("Asking question...")
    time.sleep(3)
    emit.message("The meaning of life is 42.")


def example_16():
    """Show a progress bar, but advancing with totals."""
    emit.message("We need to know!")
    emit.progress("Deciding to build a computer or upload it...")
    time.sleep(1.5)

    with emit.progress_bar("Uploading computer: planetary model", 1788, delta=False) as progress:
        for uploaded in [500, 1000, 1500, 1788]:
            progress.advance(uploaded)
            time.sleep(1.5)

    emit.progress("Asking question...")
    time.sleep(1.5)
    emit.message("The meaning of life is 42.")


def example_17():
    """Raise an error chaining other."""

    def f():
        raise ValueError("pumba")

    emit.set_mode(EmitterMode.VERBOSE)
    emit.progress("Start to work", permanent=True)
    try:
        f()
    except ValueError as exc:
        raise CraftError("Exploded while working :(") from exc


def example_18():
    """Show information that comes from a subprocess execution as a stream."""
    emit.set_mode(EmitterMode.TRACE)

    with emit.open_stream("Running a two parts something that will take time") as stream:
        cmd = "sleep 5 && echo Part 1 && sleep 5 && echo Part 2"
        subprocess.run(cmd, stdout=stream, stderr=stream, shell=True)
    emit.message("All done.")


def example_19():
    """Support some deep inside library logging."""
    emit.set_mode(EmitterMode.TRACE)

    logger = logging.getLogger("foobar.__main__")
    logger.setLevel(logging.DEBUG)
    logger.debug("Some logging in DEBUG")


def example_20():
    """Show information that comes from a subprocess execution as a stream, Windows version."""
    emit.set_mode(EmitterMode.TRACE)

    with emit.open_stream("Running a simple Windows command") as stream:
        subprocess.run(["python.exe", "-V"], stdout=stream, stderr=subprocess.STDOUT)
    emit.message("Great!")


def _run_subprocess_with_emitter(mode):
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
    temp_fh, temp_name = tempfile.mkstemp()
    with open(temp_fh, "wt", encoding="utf8") as fh:
        fh.write(example_test_sub_app)

    emit.progress("We're about to test a sub app")
    time.sleep(3)
    with emit.pause():
        subprocess.run([sys.executable, temp_name, mode.name], env={"PYTHONPATH": os.getcwd()})
        # note we cannot use `emit` while paused!
    os.unlink(temp_name)
    emit.message("All done!")


def example_21():
    """Run an app that uses emitter in a subprocess, pausing the external control, brief mode."""
    _run_subprocess_with_emitter(EmitterMode.BRIEF)


def example_22():
    """Run an app that uses emitter in a subprocess, pausing the external control, trace mode."""
    _run_subprocess_with_emitter(EmitterMode.TRACE)


def example_23():
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
    temp_fh, temp_name = tempfile.mkstemp()
    with open(temp_fh, "wt", encoding="utf8") as fh:
        fh.write(example_test_sub_app)

    emit.progress("Running subprocess...")
    cmd = [sys.executable, temp_name]
    proc = subprocess.run(cmd, env={"PYTHONPATH": os.getcwd()}, capture_output=True, text=True)
    os.unlink(temp_name)
    emit.message("Captured output:")
    for line in filter(None, itertools.chain(proc.stderr.split("\n"), proc.stdout.split("\n"))):
        emit.message(f":: {line}")


def example_24():
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


def example_25():
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


def example_26():
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
    temp_fh, temp_name = tempfile.mkstemp()
    with open(temp_fh, "wt", encoding="utf8") as fh:
        fh.write(lxd_craft_tool)

    emit.message("Application Start.")
    emit.progress("seamless progress #1")
    time.sleep(2)
    with emit.pause():
        cmd = [sys.executable, temp_name]
        subprocess.run(cmd, env={"PYTHONPATH": os.getcwd()}, capture_output=False, text=True)
        os.unlink(temp_name)
    emit.progress("seamless progress #4")
    time.sleep(2)
    emit.message("Application End.")


def _run_noisy_subprocess(mode_name, total_messages, subprocess_code):
    """Capture the output of a noisy subprocess in different modes."""
    mode = EmitterMode[mode_name.upper()]
    emit.set_mode(mode)

    temp_fh, temp_name = tempfile.mkstemp()
    with open(temp_fh, "wt", encoding="utf8") as fh:
        fh.write(subprocess_code)

    emit.progress("About to run a noisy subprocess")
    time.sleep(1)
    with emit.open_stream("Running custom Python app in unbuffered mode") as stream:
        cmd = [sys.executable, "-u", temp_name, str(total_messages)]
        subprocess.check_call(cmd, stdout=stream, stderr=stream)
    os.unlink(temp_name)
    emit.message("All done!")


def example_27(mode_name, total_messages=10):
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


def example_28(mode_name, total_messages=10):
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


def example_29(mode_name, streaming_brief):
    """Support some library logging."""
    logger = logging.getLogger()
    logger.setLevel(0)

    mode = EmitterMode[mode_name.upper()]
    emit.init(mode, "example_29", "Hi", streaming_brief=bool(int(streaming_brief)))

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


def _call_lib(logger, index):
    lib = f"lib{index}"

    time.sleep(2)
    logger.info(f"   {lib} INFO 1")
    logger.debug(f"   {lib} DEBUG 1")
    time.sleep(2)
    logger.info(f"   {lib} INFO 2")
    logger.debug(f"   {lib} DEBUG 2")
    time.sleep(2)


def example_30():
    """Message spamming, noting the different spinner behaviour"""
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
        "Now two separate messages will be spammed and no spinner appear.", permanent=True
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


# -- end of test cases

if len(sys.argv) < 2:
    print(USAGE)
    exit()

name = f"example_{int(sys.argv[1]):02d}"
func = globals().get(name)
if func is None:
    print(f"ERROR: function {name!r} not found")
    exit()

if int(sys.argv[1]) != 29:
    emit.init(EmitterMode.BRIEF, "explorator", "Greetings earthlings")
try:
    func(*sys.argv[2:])
except CraftError as err:
    emit.error(err)
except KeyboardInterrupt as exc:
    msg = "User cancelled"
    error = CraftError(msg)
    error.__cause__ = exc
    emit.error(error)
except Exception as exc:
    msg = f"Unexpected internal exception: {exc!r}"
    error = CraftError(msg)
    error.__cause__ = exc
    emit.error(error)
else:
    emit.ended_ok()
