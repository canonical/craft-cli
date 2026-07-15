.. _explanation-emit-mode:

About the appropriate mode to initiate ``emit``
===============================================

The first mandatory parameter of the ``emit`` object is ``mode``, which controls the
initial verbosity level of the system.

As the user can change the level later using global arguments when executing the
application (this is the application default level), it's recommended to use
``EmitterMode.BRIEF``, unless the application needs to honour any external configuration
or indication (e.g. a ``DEBUG`` environment variable).

The values for ``mode`` are the following attributes of the ``EmitterMode`` enumerator:

- ``EmitterMode.QUIET``: to present only error messages, if they happen
- ``EmitterMode.BRIEF``: error and info messages, with nice progress indications
- ``EmitterMode.VERBOSE``: for more verbose outputs, showing extra information to the
  user
- ``EmitterMode.DEBUG``: aimed to provide useful information to the application
  developers; this includes timestamps on each line
- ``EmitterMode.TRACE``: to also expose system-generated information (in general too
  overwhelming for debugging purposes but sometimes needed for particular analysis)
