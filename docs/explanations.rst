.. _explanations:

************
Explanations
************

About the appropriate mode to initiate ``emit``
===============================================

The first mandatory parameter of the ``emit`` object is ``mode``, which controls the initial verbosity level of the system.

As the user can change the level later using global arguments when executing the application (this is the application default level), it's recommended to use ``EmitterMode.BRIEF``, unless the application needs to honour any external configuration or indication (e.g. a ``DEBUG`` environment variable).

The values for ``mode`` are the following attributes of the ``EmitterMode`` enumerator:

- ``EmitterMode.QUIET``: to present only error messages, if they happen
- ``EmitterMode.BRIEF``: error and info messages, with nice progress indications
- ``EmitterMode.VERBOSE``: for more verbose outputs, showing extra information to the user
- ``EmitterMode.DEBUG``: aimed to provide useful information to the application developers; this includes timestamps on each line
- ``EmitterMode.TRACE``: to also expose system-generated information (in general too overwhelming for debugging purposes but sometimes needed for particular analysis)


.. _expl_log_management:

How Craft CLI manage the application logs
=========================================

Unless overridden when ``emit`` is initiated (see :ref:`how to do that <howto_other_logfile>`), the application logs will be managed by the Craft CLI library, according to the following rules:

- one log file is always produced for each application run (only exposed to the user if the application ends in error or a verbose run was requested, for example by ``--verbose``), naming the files with a timestamp so they are unique

- log files are located in a directory with the application name under the user's log directory

- only 5 files are kept, when reaching this limit the older file will be removed when creating the one for current run


.. _expl_global_args:

Global and command specific arguments
=====================================

One of the functionalities that the Dispatcher provides is global arguments handling: options that will be recognised and used no matter the position in the command line because they are not specific to any command, but global to all commands and the application itself.

For example, all these application executions are equivalent:

    <app> --verbose <command> <command-parameter>
    <app> <command> --verbose <command-parameter>
    <app> <command> <command-parameter> --verbose

The Dispatcher automatically provides the following global arguments, but more can be specified through the ``extra_global_args`` option (see :ref:`how to do that <howto_global_args>`):

- ``-h`` / ``--help``: provides a help text for the application or command
- ``-q`` / ``--quiet``: sets the ``emit`` output level to QUIET
- ``-v`` / ``--verbose``: sets the ``emit`` output level to VERBOSE
- ``--verbosity=LEVEL``: sets the ``emit`` output level to the specified level (allowed are ``quiet``, ``brief``, ``verbose``, ``debug`` and ``trace``).

Each command can also specify its own arguments parsing rules using the ``fill_parser`` method, which receives an `ArgumentParser <https://docs.python.org/dev/library/argparse.html>`_ with all its features for parsing a command line argument. The parsing result will be passed to the command on execution, as the ``parsed_args`` parameter of the ``run`` method.


Group of commands
=================

The Dispatcher's ``command_groups`` parameter is just a list ``CommandGroup`` objects, each of one grouping different commands for the different types of functionalities that may offer the application. See `its reference here <craft_cli.dispatcher.html#craft_cli.dispatcher.CommandGroup>`_, but its use is quite straightforward. E.g.::

    CommandGroup("Basic", [LoginCommand, LogoutCommand])

A list of these command groups is what is passed to the ``Dispatcher`` to run them as part of the application.

This grouping is uniquely for building the help exposed to the user, which improves the UX of the application.

When requesting the full application help, all commands will be grouped and presented in the order declared in each ``CommandGroup`` and in the list given to the ``Dispatcher``, and when requesting help for one command, other commands from the same group are suggested to the user as related to the requested one.


What are hidden and common commands?
====================================

When preparing the automatic help messages Craft CLI will consider if a message is common or hidden.

Common commands are those that surely the users will use more frequently and to be learned first, and Craft CLI will list and describe shortly after the summary in the full help.

Hidden commands, on the other hand, will not appear at all in the help messages (but will just work if used), which is useful for deprecated commands (as they will disappear in a near future they should not be advertised) or aliases (multiple commands with different names but same functionality).


Presenting messages to the user
===============================

The main interface for the application to emit messages is the ``emit`` object. It handles everything that goes to screen and to the log file, even interfacing with the formal logging infrastructure to get messages from it.

It's a singleton, just import it wherever it needs to be used::

    from craft_cli import emit

Before using it, though, it must be initiated. For example::

    emit.init(EmitterMode.BRIEF, "example-app", "Starting example app v1.")


After bootstrapping the library as shown before, and importing ``emit`` wherever is needed, all its usage is just sending information to the user. The following sections describe the different ways of doing that.


Regular messages
~~~~~~~~~~~~~~~~

The ``message`` method is for the final output of the running command.

::

    def message(self, text: str) -> None:

E.g.::

    emit.message("The meaning of life is 42.")


Progress messages
~~~~~~~~~~~~~~~~~

The ``progress`` method is to present all the messages that provide information on what the application is currently doing.

Messages shown this way are ephemeral in ``QUIET`` or ``BRIEF`` modes (overwritten by the next line) and will be truncated to the terminal's width in that case.

If a progress message is important enough that it should not be overwritten by the next ones, use ``permanent=True``.

::

    def progress(self, text: str, permanent: bool = False) -> None:

E.g.::

    emit.progress("Assembling stuff...")


Progress bar
~~~~~~~~~~~~

The ``progress_bar`` method is to be used in a potentially long-running single step of a command (e.g. a download or provisioning step).

It receives a ``text`` that should reflect the operation that is about to start, a ``total`` that will be the number to reach when the operation is completed, and optionally a ``delta=False`` to indicate that calls to ``.advance`` method should pass the total so far (by default is True, which implies that calls to ``.advance`` indicates the delta in the operation progress). Returns a context manager with the  ``.advance`` method to call on each progress.

::

    def progress_bar(self, text: str, total: Union[int, float], delta: bool = True) -> _Progresser:

E.g.::

    hasher = hashlib.sha256()
    with emit.progress_bar("Hashing the file...", filepath.stat().st_size) as progress:
        with filepath.open("rb") as fh:
            while True:
                data = fh.read(65536)
                hasher.update(data)
                progress.advance(len(data))
                if not data:
                    break


Verbose messages
~~~~~~~~~~~~~~~~

Verbose messages are useful to provide more information to the user that shouldn't be exposed when in brief mode for clarity and simplicity.

::

    def verbose(self, text: str) -> None:

E.g.::

    emit.verbose("Deleted the temporary file.")



Debug messages
~~~~~~~~~~~~~~

The ``debug`` method is to record everything that the user may not want to normally see but useful for the app developers to understand why things are failing or performing forensics on the produced logs.

::

    def debug(self, text: str) -> None:

E.g.::

    emit.debug(f"Hash calculated correctly: {hash_result}")


Trace messages
~~~~~~~~~~~~~~

The ``trace`` method is a way to expose system-generated information, about the general process or particular information, which in general would be too overwhelming for debugging purposes but sometimes needed for particular analysis.

It only produces information to the screen and into the logs if the Emitters is set to TRACE mode.

::

    def trace(self, text: str) -> None:

E.g.::

    emit.trace(f"Headers of the server response: {response.headers}")


Get messages from subprocesses
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``open_stream`` returns a context manager that can be used to get the standard output and/or error from the executed subprocess.

This way all the outputs of the subprocess will be captured by ``craft-cli`` and shown or not to the screen (according to verbosity setup) and always logged.

::

    def open_stream(self, text: str) -> _StreamContextManager:

E.g.::

    with emit.open_stream("Running ls") as stream:
        subprocess.run(["ls", "-l"], stdout=stream, stderr=stream)


Emitter modes and startup
~~~~~~~~~~~~~~~~~~~~~~~~~

The ``emit`` singleton object is first configured with an explicit call ``init()``:

E.g.::

    emit.init(
        EmitterMode.BRIEF,
        "craft",
        f"Starting craft version {__version__}",
        log_filepath=logpath,
    )

It is only after this point that ``emit`` can be used for printing. Note that the mode is typically initialised to ``EmitterMode.BRIEF``. The user can control the emitter mode through global arguments. The ``Dispatcher``, as mentioned earlier, handles global arguments (including help). However, the ``Dispatcher`` only applies emitter mode changes during ``pre_parse_args()`` when parsing the global arguments (e.g. ``--verbosity=trace``) later on in the code.

E.g.::

    dispatcher.pre_parse_args(sys.argv[1:])

The implication of the two step process above is that between ``init()`` and ``pre_parse_args()`` tracing type messages will be dropped. If you wish to support configurable message verbosity levels during early initialisation, only do that after the dispatcher's ``pre_parse_args()``.

Proposed emitter and dispatcher startup::

    emit.init(...)
    dispatcher = Dispatcher(...)
    global_args = dispatcher.pre_parse_args(sys.argv[1:])
    dispatcher.load_command(global_args)

    <early initialisation with support for verbosity levels>

    dispatcher.run()


How to easily try different message types
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There is a collection of examples in the project, in the ``examples.py`` file. Some examples are very simple, exercising only one message type, but others use different combinations so it's easy to explore more complex behaviours.

To run them using the library, a virtual environment needs to be setup::

    python3 -m venv env
    env/bin/pip install -e .[dev]
    source env/bin/activate

After that, is just a matter of running the file specifying which example to use::

    ./examples.py 18

We encourage you to adapt/improve/hack the examples in the file to play with different combinations of message types to learn and "feel" how the output would be in the different cases.


Understanding which/how messages are shown/logged
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is how texts are exposed to the screen for the different situations according to the selected verbosity level by the user running the application.

The last column of the table though is not about the screen: it indicates if the information will be present in the log created automatically by Craft CLI.

.. list-table::
   :header-rows: 1

   * -
     - QUIET
     - BRIEF
     - VERBOSE
     - DEBUG
     - TRACE
     - also to logfile
   * - ``.message(...)``
     - --
     - | stdout
       | permanent
       | plain
     - | stdout
       | permanent
       | plain
     - | stdout
       | permanent
       | plain
     - | stdout
       | permanent
       | plain
     - yes
   * - ``.progress(...)``
     - --
     - | stderr
       | transient (*)
       | plain
     - | stderr
       | permanent
       | plain
     - | stderr
       | permanent
       | timestamp
     - | stderr
       | permanent
       | timestamp
     - yes
   * - | ``.progress(..., permanent=True)``
     - --
     - | stderr
       | permanent
       | plain
     - | stderr
       | permanent
       | plain
     - | stderr
       | permanent
       | timestamp
     - | stderr
       | permanent
       | timestamp
     - yes
   * - ``.progress_bar(...)``
     - --
     - | stderr
       | transient (*)
       | plain
     - | stderr
       | permanent
       | plain
     - | stderr
       | permanent
       | timestamp
     - | stderr
       | permanent
       | timestamp
     - | first line only,
       | without progress
   * - ``.open_stream(...)``
     - --
     - | stderr
       | transient (*)
       | plain
     - | stderr
       | permanent
       | plain
     - | stderr
       | permanent
       | timestamp
     - | stderr
       | permanent
       | timestamp
     - yes
   * - ``.verbose(...)``
     - --
     - --
     - | stderr
       | permanent
       | plain
     - | stderr
       | permanent
       | timestamp
     - | stderr
       | permanent
       | timestamp
     - yes
   * - ``.debug(...)``
     - --
     - --
     - --
     - | stderr
       | permanent
       | timestamp
     - | stderr
       | permanent
       | timestamp
     - yes
   * - ``.trace(...)``
     - --
     - --
     - --
     - --
     - | stderr
       | permanent
       | timestamp
     - | only when
       | level=trace
   * - | **captured logs**
       | (level > ``logging.DEBUG``)
     - --
     - --
     - | stderr
       | permanent
       | plain
     - | stderr
       | permanent
       | timestamp
     - | stderr
       | permanent
       | timestamp
     - yes
   * - | **captured logs**
       | (level == ``logging.DEBUG``)
     - --
     - --
     - --
     - | stderr
       | permanent
       | timestamp
     - | stderr
       | permanent
       | timestamp
     - yes
   * - | **captured logs**
       | (level < ``logging.DEBUG``)
     - --
     - --
     - --
     - --
     - | stderr
       | permanent
       | timestamp
     - | only when
       | level=trace

(*) when redirected to a file it doesn't make sense to have "transient" messages, so 'progress' messages will always end in a newline, and 'progress_bar' will just send its message line but without the progress indication.

When the application ends in error it should call the ``emit.error()`` method passing a ``CraftError`` instance. According to the verbosity level some information will be exposed or not. The following table details what happens in each case: which ``CraftError`` attribute is exposed and how the information is shown (similar to the other table above):

.. list-table::
   :header-rows: 1

   * -
     - QUIET
     - BRIEF
     - VERBOSE
     - DEBUG
     - TRACE
     - also to logfile
   * - the error message
     - yes
     - yes
     - yes
     - yes
     - yes
     - yes
   * - full tracebacks
     - no
     - no
     - no
     - yes
     - yes
     - yes
   * - ``.details``
     - no
     - no
     - no
     - yes
     - yes
     - yes
   * - ``.resolution``
     - yes
     - yes
     - yes
     - yes
     - yes
     - yes
   * - ``.docs_url``
     - yes
     - yes
     - yes
     - yes
     - yes
     - yes
   * - how is it shown
     - | stderr
       | permanent
       | plain
     - | stderr
       | permanent
       | plain
     - | stderr
       | permanent
       | plain
     - | stderr
       | permanent
       | timestamp
     - | stderr
       | permanent
       | timestamp
     - yes
