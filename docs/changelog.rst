:tocdepth: 2

***************
Changelog
***************

See the `Releases page`_ on GitHub for a complete list of commits that are
included in each version.

2.13.0 (2024-Dec-16)
--------------------

- Show error details in every mode except quiet.

2.12.0 (2024-Dec-13)
--------------------

- Remove the ``assert_error`` pytest plugin method. For checking errors, we
  recommend using ``capsys`` instead.
- Add a ``confirm`` method to the emitter for asking a yes-no question.

2.11.0 (2024-Dec-12)
--------------------

- Hide positional arguments from extended help if the argument does not
  provide any help text.
- Remove markdown code block back ticks from plain text help output.
- Add a new ``assert_error`` to the pytest plugin for testing.

2.10.1 (2024-Nov-11)
--------------------

- Fix an issue where setting an ``Emitter`` to the same mode multiple times
  resulted in multiple greetings.
- Hidden commands can no longer show up as suggested alternatives when an
  invalid command is entered by the user.

2.10.0 (2024-Oct-31)
--------------------
- Support adding a link to documentation in help messages.

2.9.0 (2024-Oct-22)
-------------------

- The ``Dispatcher.pre_parse_args()`` method now accepts an ``app_config``
  parameter, which is used to instantiate the command that will be validated.

2.8.0 (2024-Oct-10)
-------------------
- Positional arguments are now displayed in 'help' outputs.
- The terminal cursor is now hidden during execution.

2.7.0 (2024-Sep-05)
-------------------
- Add a new ``CraftCommandError`` class for errors that wrap command output
- Fix the reporting of error messages containing multiple lines

2.6.0 (2024-Jul-02)
-------------------
- Disable exception chaining for help/usage exceptions
- Support a doc slug in CraftError in addition to full urls

.. _Releases page: https://github.com/canonical/craft-cli/releases
