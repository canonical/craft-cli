# Craft CLI

A Command Line Client builder that follows Canonical's guidelines for a command line
interface defined [in this forum post](https://discourse.ubuntu.com/c/design/cli-guidelines/62).

The library provides two main functionalities: 

- a framework to define and execute application commands, which involves argument parsing and the provision of help texts

- infrastructure to handle the terminal and present all the outputs for the different application needs


# Documentation

The documentation is in Read The Docs, [check it out](https://craft-cli.readthedocs.io).


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
