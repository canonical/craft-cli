.. _use_completion:

Use the completion module
=========================

Craft-cli provides a completion module for auto-generating bash completion scripts for
applications using its :py:class:`Dispatcher`.

In order to invoke it, the application needs to have a public function that returns
some basic information about itself. All applications must provide their
:py:class:`Dispatcher` and a configuration to initialise commands with. By default,
craft-cli commands don't need to be initialised with anything, so this would be
``None`` in the basic case.

For a project named "testcraft", create the file :file:`testcraft/application.py` and
add the following content:

.. code:: python

    from craft_cli import Dispatcher

    def get_dispatcher() -> Dispatcher:
        """Fill out this function to create the application's dispatcher"""

    def get_app_info() -> tuple[Dispatcher, None]:
        return get_dispatcher(), None

Once the function is made, the completion module can be invoked to create the
completion file:

.. code:: shell

    python3 -m craft_cli.completion testcraft testcraft.application:get_app_info > completion.sh

Applications using craft-application
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Commands from `craft-application`_ need their ``app_config`` dictionary in order to be
initialised. To handle this, return the ``app_config`` alongside the application's
:py:class:`Dispatcher` object:

.. code:: python

    from craft_cli import Dispatcher
    from typing import Any

    def get_app() -> MyApplication:
        """Fill out this function to create an application"""

    def get_dispatcher() -> Dispatcher:
        """Fill out this function to create the application's dispatcher"""

    def get_app_info() -> tuple[Dispatcher, dict[str, Any]]:
        app = get_app()
        dispatcher = get_dispatcher()
        return dispatcher, app.app_config

.. _craft-application: https://github.com/canonical/craft-application
