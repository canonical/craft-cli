.. _use_global_args:

Define and use other global arguments
=====================================

To define more automatic global arguments than the ones provided automatically by ``Dispatcher`` (see :ref:`this explanation <expl_global_args>` for more information), use the ``GlobalArgument`` object to create all you need and pass them to the ``Dispatcher`` at creation time.

Check :class:`craft_cli.dispatcher.GlobalArgument` for more information about the parameters needed, but it's very straightforward to create these objects. E.g.::

    ga_sec = GlobalArgument("secure_mode", "flag", "-s", "--secure", "Run the app in secure mode")

To use it, just pass a list of the needed global arguments to the dispatcher using the ``extra_global_args`` option::

    dispatcher = Dispatcher(..., extra_global_args=[ga_sec])

The ``dispatcher.pre_parse_args`` method returns the global arguments already parsed, as a dictionary. Use the name you gave to the global argument to check for its value and react properly. E.g.::

    global_args = dispatcher.pre_parse_args(sys.argv[1:])
    app_config.set_secure_mode(global_args["secure_mode"])
