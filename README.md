# Craft CLI

A Command Line Client builder that follows Canonical's guidelines for a command line
interface defined [in this forum post](https://discourse.ubuntu.com/c/design/cli-guidelines/62).

The main entry point for its usage is the `emit` object, which will handled all the outputs for the different application needs. See the [Usage](https://github.com/canonical/craft-cli/#usage) section below for more details.

We still need to add some functionality to simplify the apps using the lib, check issues [43](https://github.com/canonical/craft-cli/issues/43), [44](https://github.com/canonical/craft-cli/issues/44) and [45](https://github.com/canonical/craft-cli/issues/45).

# Setup

The main interface for the application to emit messages is the `emit` object.  It handles everything that goes to screen and to the log file, even interfacing with the formal logging infrastructure to get messages from it.

It's a singleton, just import it wherever it needs to be used:

```python
from craft_cli import emit
```

It needs to be initiated before first usage, though, passing the verboseness mode (`QUIET`, `NORMAL`, `VERBOSE` or `TRACE`), the app name, and a greeting message (that will be always logged and shown in the screen in the more verbose modes, very useful to indicate the running version of the application):

```python
emit.init(EmitterMode.NORMAL, "my-app-name", f"Starting super app v3")
```

After that, `emit` can be used in different ways, explained below.

It's always a good idea to wrap all the app execution in a comprehensive try/except block to produce proper error messages when something goes bad (note that in the future this functionality will be included in `craft-cli` itself):

```python
from craft_cli import emit, CraftError
...
try:
    (all app execution)
except Exception as err:
    error = CraftError(f"charmcraft internal error: {err!r}")
    error.__cause__ = err
    emit.error(error)
else:
    emit.ended_ok()
```


# Usage

After bootstrapping the library as shown above, and importing `emit` wherever is needed, all the usage is just sending information to the user. This section describes the different ways of doing that.


## Regular messages

The `message` metod is for the final output of the running command.

If there is important information that needs to be shown to the user in the middle of the execution (and not overwritten by other messages) this method can be also used but passing `intermediate=True`.

```python
    def message(self, text: str, intermediate: bool = False) -> None:
```

E.g.:

```python
emit.message("The meaning of life is 42.")
```


## Progress messages

The `progress` method is for all the progress messages intended to provide information that the machinery is running and doing what. 

Messages shown this way are ephemeral in `QUIET` or `NORMAL` modes (overwritten by the next line) and will be truncated to the terminal's width.

```python
    def progress(self, text: str) -> None:
```

E.g.:

```python
emit.progress("Assembling stuff...")
```

## Progress bar

The `progress_bar` method is to be used in a potentially long-running single step of a command (e.g. a download or provisioning step).

FIXME

```python
    def progress_bar(self, text: str, total: Union[int, float], delta: bool = True) -> _Progresser:
```

        Returns a context manager with a `.advance` method to call on each progress (passing the
        delta progress, unless delta=False here, which implies that the calls to `.advance` should
        pass the total so far).
        """

E.g.:

```python

```



## Trace/debug messages

    - `trace`: for all the messages that may used by the *developers* to do any debugging on
    the application behaviour and/or logs forensics.

FIXME
what is it intended for
how to use it (params explained)
GIF with example

    - `trace`: for all the messages that may used by the *developers* to do any debugging on
    the application behaviour and/or logs forensics.


E.g.:

```python

```

## Get messages from subprocesses

FIXME
what is it intended for
how to use it (params explained)
GIF with example

    def open_stream(self, text: str):
        """Open a stream context manager to get messages from subprocesses."""



E.g.:

```python

```

## How to easily test different combinations

FIXME: examples.py


33444  python3 -m venv env
33445  env/bin/pip install -e .[dev]
33448  source env/bin/activate
33449  make tests
33450  make test-units
33451  ./examples.py 18



# Documentation

The documentation is in Read The Docs, [check it out](https://craft-cli.readthedocs.io).
FIXME: check what is built

# Contributing

A `Makefile` is provided for easy interaction with the project. To see
all available options run:

    make help


## Running tests

To run all tests in the suite run:

    make tests


## Verifying documentation changes

To locally verify documentation changes run:

    make docs

After running, newly generated documentation shall be available at
`./docs/_build/html/`.


# License

Free software: GNU Lesser General Public License v3
