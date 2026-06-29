.. _explanation-command-groups:

Group of commands
=================

The Dispatcher's ``command_groups`` parameter is just a list ``CommandGroup`` objects,
each of one grouping different commands for the different types of functionalities that
may offer the application. See :class:`craft_cli.CommandGroup` for its reference, but its use is quite
straightforward. E.g.::

    CommandGroup("Basic", [LoginCommand, LogoutCommand])

A list of these command groups is what is passed to the ``Dispatcher`` to run them as
part of the application.

This grouping is uniquely for building the help exposed to the user, which improves the
UX of the application.

When requesting the full application help, all commands will be grouped and presented in
the order declared in each ``CommandGroup`` and in the list given to the ``Dispatcher``,
and when requesting help for one command, other commands from the same group are
suggested to the user as related to the requested one.
