from typing import BinaryIO

from typing_extensions import Self

# Inheritance does nothing in type stubs, but it signals to static type checkers
# that this object is capable of binary writes. All that Python itself actually
# cares to see for this is a `fileno` method, which is actually implemented.
class StreamHandle(BinaryIO):
    """A handle on a writable stream.

    All messages written to this stream will be emitted.
    """

    def __enter__(self) -> Self: ...
    def __exit__(self, *_args: object) -> None: ...
    def fileno(self) -> int: ...
