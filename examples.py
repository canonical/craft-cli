#!/bin/env python3

import logging
import subprocess
import sys
import time

from craft_cli import CraftError, EmitterMode, emit


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
    """Show a progress bar."""
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
    """Show a debug message when it makes sense."""
    # note this will show the greeting twice, as it's setting the mode twice (which
    # won't happen IRL)
    for mode in EmitterMode:
        emit.set_mode(mode)
        time.sleep(0.1)
        emit.trace(f"Debug message when mode={mode}")


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
    emit.message(msg, intermediate=True)

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
    emit.message("Building computer...", intermediate=True)
    time.sleep(1)
    emit.progress("Assembling stuff...")
    time.sleep(1)
    emit.message("Asking question...", intermediate=True)
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
        emit.message(f"====== mode: {mode}")
        logger.error("Some logging in ERROR")
        logger.info("Some logging in INFO")
        logger.debug("Some logging in TRACE")


def example_15():
    """Specific combination of long message with other progress, in verbose."""
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
    emit.message("Start to work", intermediate=True)
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


# -- end of test cases

if len(sys.argv) != 2:
    print("USAGE: explorator.py <test_id>  # ej 04")
    exit()

name = f"example_{int(sys.argv[1]):02d}"
func = globals().get(name)
if func is None:
    print(f"ERROR: function {name!r} not found")
    exit()

emit.init(EmitterMode.NORMAL, "explorator", "Greetings earthlings")
try:
    func()
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
