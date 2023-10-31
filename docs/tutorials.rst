
*********
Tutorials
*********

Run a command based application with craft-cli
==============================================

This tutorial will explain how to use Craft CLI to run an application that is based on commands.

Along the way you will define a simple command (named ``unlink``, with the functionality of removing files), and call the appropriate library mechanisms for that command to be executed when running the application.


Prerequisites
-------------

Craft CLI is a standard Python library, so the best way to have it available is installed in a virtual environment.

The first step, then, is to create a virtual environment (you may skip this test if you already have one)::


    $ python3 -m venv env

Note that Python 3.8 or 3.9 are the supported versions.

Then enable the virtual environment and install Craft CLI::

    $ source env/bin/activate
    $ pip install craft-cli



Define the command and run it using the Dispatcher
--------------------------------------------------

First start with a class sub-classing ``BaseCommand`` with the appropriate attributes to name it and have automatic help texts, then provide a ``fill_parser`` method to declare what arguments are possible for this command, and finally a ``run`` method where the "real" functionality is implemented::

    import pathlib
    import textwrap
    import sys
    from craft_cli import (
        ArgumentParsingError,
        BaseCommand,
        CommandGroup,
        CraftError,
        Dispatcher,
        EmitterMode,
        ProvideHelpException,
        emit,
    )


    class RemoveFileCommand(BaseCommand):
        """Remove the indicated file."""

        name = "unlink"
        help_msg = "Remove the indicated file."
        overview = textwrap.dedent("""
            Remove the indicated file.

            A file needs to be indicated. It is an argument error if the path does not exist
            or it's a directory.

            It will return successfully if the file was properly removed.
        """)

        def fill_parser(self, parser):
            """Add own parameters to the general parser."""
            parser.add_argument("filepath", type=pathlib.Path, help="The file to be removed")

        def run(self, parsed_args):
            """Run the command."""
            if not parsed_args.filepath.exists() or parsed_args.filepath.is_dir():
                raise ArgumentParsingError("The indicated path is not a file or does not exist.")
            try:
                parsed_args.filepath.unlink()
            except Exception as exc:
                raise CraftError(f"Problem removing the file: {exc}.")

            emit.message("File removed successfully.")

Then initiate the ``emit`` object and call the ``Dispatcher`` functionality::

    emit.init(EmitterMode.BRIEF, "example-app", "Starting example app v1.")
    command_groups = [CommandGroup("Basic", [RemoveFileCommand])]
    summary = "Example application for the craft-cli tutorial."

    try:
        dispatcher = Dispatcher("example-app", command_groups, summary=summary)
        dispatcher.pre_parse_args(sys.argv[1:])
        dispatcher.load_command(None)
        dispatcher.run()
    except (ArgumentParsingError, ProvideHelpException) as err:
        print(err, file=sys.stderr)  # to stderr, as argparse normally does
        emit.ended_ok()
    except CraftError as err:
        emit.error(err)
    except KeyboardInterrupt as exc:
        error = CraftError("Interrupted.")
        error.__cause__ = exc
        emit.error(error)
    except Exception as exc:
        error = CraftError(f"Application internal error: {exc!r}")
        error.__cause__ = exc
        emit.error(error)
    else:
        emit.ended_ok()

Finally, put both chunks of code in a ``example-app.py`` file, and (having the virtual environment you prepared at the beginning still activated), run it. You should see the help message for the whole application (as a command is missing, which would be the same output if you pass the ``help``, ``-h`` or ``--help`` parameters)::

    $ python example-app.py
    Usage:
        example-app [help] <command>

    Summary:    Example application for the craft-cli tutorial.

    Global options:
           -h, --help:  Show this help message and exit
        -v, --verbose:  Show debug information and be more verbose
          -q, --quiet:  Only show warnings and errors, not progress
          --verbosity:  Set the verbosity level to 'quiet', 'brief',
                        'verbose', 'debug' or 'trace'",

    Starter commands:

    Commands can be classified as follows:
              Example:  unlink

    For more information about a command, run 'example-app help <command>'.
    For a summary of all commands, run 'example-app help --all'.

Ask help for specifically for the command::

    $ python example-app.py help unlink
    Usage:
        example-app unlink [options] <filepath>

    Summary:
        Remove the indicated file.

        A file needs to be indicated. It is an argument error if the path does not exist
        or it's a directory.

        It will return successfully if the file was properly removed.

    Options:
           -h, --help:  Show this help message and exit
        -v, --verbose:  Show debug information and be more verbose
          -q, --quiet:  Only show warnings and errors, not progress
          --verbosity:  Set the verbosity level to 'quiet', 'brief',
                        'verbose', 'debug' or 'trace'",

    For a summary of all commands, run 'example-app help --all'.

Time to run the command on a file, you should see the successful message::

    $ touch testfile
    $ ls testfile
    testfile
    $ env/bin/python example-app.py unlink testfile
    File removed successfully.
    $ ls testfile
    ls: cannot access 'testfile': No such file or directory

Explore different error situations, first trying to remove a directory, then trying to remove a file but with "unexpected" problems::

    $ mkdir testdir
    $ python example-app.py unlink testdir
    The indicated path is not a file or does not exist.

    $ touch /tmp/testfile
    $ sudo chown root /tmp/testfile
    $ python example-app.py unlink /tmp/testfile
    Problem removing the file: [Errno 1] Operation not permitted: '/tmp/testfile'.
    Full execution log: '/home/user/.cache/example-app/log/example-app-20220114-120745.861866.log'

Congratulations! You have built a complete application with good UX by using Craft CLI and implementing the functionality in one command.
