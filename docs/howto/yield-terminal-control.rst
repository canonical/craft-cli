.. _yield_terminal_control:

Temporarily allow another application to control the terminal
=============================================================

To be able to run another application (another process) without interfering in the use of the terminal between the main application and the sub-executed one, you need to pause the emitter::

    with emit.pause():
        subprocess.run(["someapp"])

When the emitter is paused the terminal is freed, and the emitter does not have control on what happens in the terminal there until it's resumed, not even for logging purposes.

The normal behaviour is resumed when the context manager exits (even if an exception was raised inside).
