.. _explanation-log-management:

.. _expl_log_management:

How Craft CLI manage the application logs
=========================================

Unless overridden when ``emit`` is initiated (see :ref:`how to do that
<change_logfile>`), the application logs will be managed by the Craft CLI library,
according to the following rules:

- one log file is always produced for each application run (only exposed to the user if
  the application ends in error or a verbose run was requested, for example by
  ``--verbose``), naming the files with a timestamp so they are unique

- log files are located in a directory with the application name under the user's log
  directory

- only 5 files are kept, when reaching this limit the older file will be removed when
  creating the one for current run
