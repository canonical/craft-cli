.. _change_return_code:

End the application with different return codes
===============================================

To enable the application to return different return codes in different situations, you need wrap the Dispatcher in a specific way (having different return codes in the different situations), to take in consideration the returned value from the command's run, and of course make the application to actually return the specific value.

In the following code structure we see all these effects at once::

    try:
        ...
        retcode = dispatcher.run()
        if retcode is None:
            retcode = 0
    except ArgumentParsingError as err:
        print(err, file=sys.stderr)  # to stderr, as argparse normally does
        emit.ended_ok()
        retcode = 1
    except ProvideHelpException as err:
        print(err, file=sys.stderr)  # to stderr, as argparse normally does
        emit.ended_ok()
        retcode = 0
    except CraftError as err:
        emit.error(err)
        retcode = err.retcode
    except KeyboardInterrupt as exc:
        error = CraftError("Interrupted.")
        error.__cause__ = exc
        emit.error(error)
        retcode = 1
    except Exception as exc:
        error = CraftError(f"Application internal error: {exc!r}")
        error.__cause__ = exc
        emit.error(error)
        retcode = 1
    else:
        emit.ended_ok()
    sys.exit(retcode)

In detail:

- the return code from the command's execution is bound when calling ``dispatcher.run``, supporting the case of it not returning anything (defaults to ``0``)

- have different return codes assigned for the different ``except`` situations, with two particular cases: for ``ProvideHelpException`` it's ``0`` as it's a normal exit situation when the user requested for help, and for ``CraftError`` where the return code is taken from the exception itself

- a ``sys.exit`` at the very end for the process to return the value
