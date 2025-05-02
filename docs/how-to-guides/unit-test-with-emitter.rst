.. _unit_test_with_emitter:

Create unit tests for code that uses Craft CLI's Emitter
========================================================

The library provides two fixtures that simplifies the testing of code using the Emitter when using ``pytest``.

One of the fixtures (``init_emitter``) is even set with ``autouse=True``, so it will automatically initialise the Emitter and tear it down after each test. This way there is nothing special you need to do in your code when testing it, just use it.

The other fixture (``emitter``) is very useful to test code interaction with Emitter. It provides an internal recording emitter that has several methods which help to test its usage.

The following example shows a simple usage, please refer to :class:`craft_cli.pytest_plugin.RecordingEmitter` for more information about the provided functionality::

    def test_super_function(emitter):
        """Check the super function."""
        result = super_function(42)
        assert result == "Secret of life, etc."
        emitter.assert_trace("Function properly called with magic number.")
