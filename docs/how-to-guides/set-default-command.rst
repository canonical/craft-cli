.. _set_default_command:

Set a default command for the application
=========================================

To allow the application to run a command if none was given in the command line, you need to set a default command in the application when instantiating :class:`craft_cli.dispatcher.Dispatcher`::

    dispatcher = Dispatcher(..., default_command=MyImportantCommand)

This way ``craft-cli`` will run the specified command if none was given, e.g.::

    $ my-super-app

And even run the specified default command if options are given for that command::

    $ my-super-app --important-option
