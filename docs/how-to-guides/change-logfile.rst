.. _change_logfile:

Use a different logfile structure than the default
==================================================

To override :ref:`the default management of application log files <expl_log_management>`, a file path can be specified when initiating the ``emit`` object, using the ``log_filepath`` parameter::

    emit.init(mode, appname, greeting, log_filepath)

Note that if you use this option, is up to you to provide proper management of those files (e.g. to rotate them).
