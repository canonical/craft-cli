from typing_extensions import Self

class Progresser:
    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        _traceback: object,
    ) -> None: ...
    def tick(self) -> None:
        """Increase progress by one."""

    def inc(self, delta: int) -> None:
        """Increase progress by `delta`.

        Must be a positive number.

        :raises OverflowError: If a negative number is provided.
        """

    def println(self, text: str) -> None:
        """Display a message alongside current progress.

        This method must be used instead of any emitting methods from an `Emitter`.
        It will share verbosity level with the `Emitter` that spawned it, and all
        messages will be permanent.
        """

    def progress(self) -> int:
        """How much progress is complete so far."""
