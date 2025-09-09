:tocdepth: 2

Changelog
=========

See the `Releases page`_ on GitHub for a complete list of commits that are
included in each version.

.. _release-3.2.0:

3.2.0 (2025-09-09)
-------------------

New features:

- Make :py:meth:`.Emitter.report_error()` public.
- Add a :py:meth:`.Emitter.warning()` method for indicating recoverable errors or
  potentially undesired behavior to the user.

.. _release-3.1.2:

3.1.2 (2025-07-22)
-------------------

Bug fixes:

- Fixed the many spurious errors when stopping the printer during tests.

.. _release-3.1.1:

3.1.1 (2025-07-18)
-------------------

Bug fixes:

- Correct a typo in the deprecation notice for using the default command.

.. _release-3.1.0:

3.1.0 (2025-07-17)
-------------------

New features:

- To improve readability, multi-line details in error messages now start on a new line.

Bug fixes:

- `#334`_ The cursor is now always displayed after Craft CLI exits.

Deprecations:

- Add a deprecation notice when the dispatcher's default command is used.
  Support for default commands will be removed in a future release.

3.0.0 (2025-03-27)
-------------------

Breaking changes

    - Deprecates support for Python 3.8 and adds support for Python 3.11
      and 3.12.

New features

    - Add an ``append_to_log`` method to the emitter, which reads from a file
      and dumps it directly into the log.
    - Add a ``log_filepath`` read-only property to the emitter.

2.15.0 (2025-01-23)
--------------------

This release deprecates craft-cli 2.14.0, which is considered broken and
should not be used.

- Fixes an error with the ``completion`` module's interaction with newer
  projects based on craft-application.

2.14.0 (2025-01-21)
--------------------

- Add a ``prompt`` method to the emitter for asking user for an input.
- Add a ``completion`` module for generating bash auto-completion scripts.

2.13.0 (2024-12-16)
--------------------

- Show error details in every mode except quiet.

2.12.0 (2024-12-13)
--------------------

- Remove the ``assert_error`` pytest plugin method. For checking errors, we
  recommend using ``capsys`` instead.
- Add a ``confirm`` method to the emitter for asking a yes-no question.

2.11.0 (2024-12-12)
--------------------

- Hide positional arguments from extended help if the argument does not
  provide any help text.
- Remove markdown code block back ticks from plain text help output.
- Add a new ``assert_error`` to the pytest plugin for testing.

2.10.1 (2024-11-11)
--------------------

- Fix an issue where setting an ``Emitter`` to the same mode multiple times
  resulted in multiple greetings.
- Hidden commands can no longer show up as suggested alternatives when an
  invalid command is entered by the user.

2.10.0 (2024-10-31)
--------------------
- Support adding a link to documentation in help messages.

2.9.0 (2024-10-22)
-------------------

- The ``Dispatcher.pre_parse_args()`` method now accepts an ``app_config``
  parameter, which is used to instantiate the command that will be validated.

2.8.0 (2024-10-10)
-------------------
- Positional arguments are now displayed in 'help' outputs.
- The terminal cursor is now hidden during execution.

2.7.0 (2024-09-05)
-------------------
- Add a new ``CraftCommandError`` class for errors that wrap command output
- Fix the reporting of error messages containing multiple lines

2.6.0 (2024-07-02)
-------------------
- Disable exception chaining for help/usage exceptions
- Support a doc slug in CraftError in addition to full urls

.. _Releases page: https://github.com/canonical/craft-cli/releases

.. _#334: https://github.com/canonical/craft-cli/issues/334
