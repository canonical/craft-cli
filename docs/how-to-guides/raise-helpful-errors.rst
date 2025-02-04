.. _raise_helpful_errors:

Raise more informational errors
===============================

To provide more information to the user in case of an error, you can use the ``CraftError`` exception provided by the ``craft-cli`` library.

So, in addition of just passing a message to the user...

::

    raise CraftError("The indicated file does not exist.")

...you can provide more information:

- ``details``: full error details received from a third party or extended information about the situation, useful for debugging but not to be normally shown to the user. E.g.::

    raise CraftError(
        "Cannot access the indicated file.",
        details=f"File permissions: {oct(filepath.stat().st_mode)}")

    raise CraftError(
        f"Server returned bad code {error_code}",
        details=f"Full server response: {response.content!r}")


- ``resolution``: an extra line indicating to the user how the error may be fixed or avoided. E.g.::

    raise CraftError(
        "Cannot remove the directory.",
        resolution="Confirm that the directory is empty and has proper permissions.")

- ``docs_url``: an URL to point the user to documentation. E.g.::

    raise CraftError(
        "Invalid configuration: bad version value.",
        docs_url="https://mystuff.com/docs/how-to-migrate-config")

- ``reportable``: if an error report should be sent to some error-handling backend (like Sentry). E.g.::

    raise CraftError(
        f"Unexpected subprocess return code: {proc.returncode}.",
        reportable=True)

- ``retcode``: the code to return when the application finishes (see :ref:`how to use this when wrapping Dispatcher <change_return_code>`)

You should use any combination of these, as looks appropriate.

For further information reported to the user and/or sent to the log file, you should create ``CraftError`` specifying the original exception (if any). E.g.::

    try:
        ...
    except IOError as exc:
        raise CraftError(f"Error when frunging the perculux: {exc}") from exc

Finally, if you want to build a hierarchy of errors in the application, you should start the tree inheriting ``CraftError`` to use this functionality.
