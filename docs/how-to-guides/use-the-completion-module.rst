.. _use_the_completion_module:

Use the completion module
=========================

Craft CLI provides the completion module, which auto-generates Bash completion scripts
for apps.

Write the app info getter
-------------------------

To invoke the module, an app needs to have a public function that returns some basic
information about itself. The app must provide a
:py:class:`~craft_cli.dispatcher.Dispatcher` with a configuration to initialise
commands with. By default, Craft CLI commands don't need to be initialised with
anything, so this would be ``None`` in the basic case.

The :py:class:`~craft_cli.dispatcher.Dispatcher` is where the commands themselves are
pulled in and transformed into entries for the Bash script. The commands inside the
:py:class:`~craft_cli.dispatcher.Dispatcher` are initialised and then parsed for their
options and inputs.

The purpose of the getter is to give the module an entry point into your application
for it to gather the necessary information to build a completion script.

For a project named Testcraft, create the file :file:`testcraft/application.py` and
add the following content:

.. code:: python

    from craft_cli import Dispatcher

    def get_dispatcher() -> Dispatcher:
        """Fill out this function to create the application's dispatcher"""

    def get_app_info() -> tuple[Dispatcher, None]:
        # Returning the Dispatcher and no initialisation config
        return get_dispatcher(), None

Create the completion script
----------------------------

Once the function is made, the completion module can be invoked to create the
completion file:

.. code:: shell

    python3 -m craft_cli.completion testcraft testcraft.application:get_app_info > completion.sh

Applications using craft-application
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Commands from `craft-application`_ need their corresponding ``Application``
object's ``app_config`` in order to be initialised. To handle this, return the
``app_config`` alongside the application's :py:class:`~craft_cli.dispatcher.Dispatcher`
object:

.. code:: python

    from craft_application import Application, ServiceFactory
    from craft_cli import Dispatcher
    from typing import Any

    from my_app import APP_METADATA, commands
    def get_app() -> Application:
        """Replace this function with a function that instantiates your app."""
        services = ServiceFactory(app=APP_METADATA)
        app = Application(app=APP_METADATA, services=services)
        commands.fill_command_groups(app)
        return app

    def get_dispatcher() -> Dispatcher:
        """Fill out this function to create the application's dispatcher"""

    def get_app_info() -> tuple[Dispatcher, dict[str, Any]]:
        app = get_app()
        dispatcher = get_dispatcher()
        return dispatcher, app.app_config

.. _craft-application: https://github.com/canonical/craft-application
