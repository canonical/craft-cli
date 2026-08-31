.. _explanation-global-args:

.. _expl_global_args:

Global and command specific arguments
======================================

One of the functionalities that the Dispatcher provides is global arguments handling:
options that will be recognised and used no matter the position in the command line
because they are not specific to any command, but global to all commands and the
application itself.

For example, all these application executions are equivalent:

    <app> --verbose <command> <command-parameter>
    <app> <command> --verbose <command-parameter>
    <app> <command> <command-parameter> --verbose

The Dispatcher automatically provides the following global arguments, but more can be
specified through the ``extra_global_args`` option (see :ref:`how to do that
<use_global_args>`):

- ``-h`` / ``--help``: provides a help text for the application or command
- ``-q`` / ``--quiet``: sets the ``emit`` output level to QUIET
- ``-v`` / ``--verbose``: sets the ``emit`` output level to VERBOSE
- ``--verbosity=LEVEL``: sets the ``emit`` output level to the specified level (allowed
  are ``quiet``, ``brief``, ``verbose``, ``debug`` and ``trace``).

Each command can also specify its own arguments parsing rules using the ``fill_parser``
method, which receives an `ArgumentParser
<https://docs.python.org/dev/library/argparse.html>`_ with all its features for parsing
a command line argument. The parsing result will be passed to the command on execution,
as the ``parsed_args`` parameter of the ``run`` method.
