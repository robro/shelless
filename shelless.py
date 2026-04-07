"""shell features without 'shell=True'


piping:

ls | grep ...

pipe(cmd("ls"), cmd("grep", ...))


process substitution:

diff <(zcat ... | sed ...) <(zcat ... | sed ...)

cmd(
    "diff",
    pipe(cmd("zcat", ...), cmd("sed", ...)),
    pipe(cmd("zcat", ...), cmd("sed", ...))
)
"""

from abc import ABC, abstractmethod
from subprocess import CompletedProcess, Popen, PIPE
from typing import Any, IO, Iterable, List, Optional, Type, TypeVar, Union, overload
from typing import Sequence

T = TypeVar("T")


class Command(Sequence[T], ABC):
    """Abstract base class for runnable shell sequences."""

    _valid_types: List[Type[Any]]

    def __init__(self, items: Iterable[T]):
        self._items: List[T] = []
        for item in items:
            self._validate(item)
            self._items.append(item)

    def _validate(self, value: Any) -> None:
        if any(isinstance(value, t) for t in self._valid_types):
            return
        t_self = type(self).__name__
        t_value = type(value).__name__
        t_valid = " or ".join([t.__name__ for t in self._valid_types])
        raise TypeError(f'{t_self} can only contain {t_valid} (not "{t_value}")')

    @abstractmethod
    def open_process(self) -> "Popen[bytes]": ...

    def __len__(self) -> int:
        return len(self._items)

    @overload
    def __getitem__(self, index: int) -> T:
        # return self._items[index]
        pass

    @overload
    def __getitem__(self, index: slice) -> "Command[T]":
        # return type(self)(self._items[index.start : index.stop : index.step])
        pass

    def __getitem__(self, index: object) -> Union["Command[T]", T]:
        if isinstance(index, int):
            return self._items[index]
        if isinstance(index, slice):
            return type(self)(self._items[index.start : index.stop : index.step])
        t_self = type(self).__name__
        t_index = type(index).__name__
        raise TypeError(f"{t_self} indices must be integers or slices, not {t_index}")

    def __add__(self, other: "Command[T]") -> "Command[T]":
        if isinstance(other, type(self)):
            return type(self)(self._items + other._items)
        t_self = type(self).__name__
        t_other = type(other).__name__
        raise TypeError(f'can only concatenate {t_self} (not "{t_other}") to {t_self}')

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join(x.__repr__() for x in self._items)})"


CmdArg = Union[Command[Any], str]


class Cmd(Command[CmdArg]):
    """Represents a single program command.

    Nested command arguments represent shell process substitution.
    """

    _valid_types: List[Type[Any]] = [Command, str]

    def __init__(self, args: Iterable[CmdArg]):
        super().__init__(args)

    def open_process(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]":
        """Open a process for this command and return it."""
        if not self._items:
            raise Exception("cannot open process of empty command.")
        fds: List[int] = []
        args: List[str] = []
        procs: List[Popen[bytes]] = []
        for arg in self._items:
            if isinstance(arg, str):
                args.append(arg)
            else:
                proc = arg.open_process()
                fd = proc.stdout.fileno() if proc.stdout else -1
                fds.append(fd)
                args.append(f"/dev/fd/{fd}")
                procs.append(proc)

        process = Popen(args, stdin=stdin, stdout=PIPE, stderr=PIPE, pass_fds=fds)
        for proc in procs:
            proc.stdout.close() if proc.stdout else None
        return process

    def __str__(self) -> str:
        return " ".join(a if isinstance(a, str) else f"<({a})" for a in self._items)


class Pipeline(Command[Cmd]):
    """Represents a chain of piped program commands."""

    _valid_types: List[Type[Any]] = [Cmd]

    def __init__(self, cmds: Iterable[Cmd]):
        super().__init__(cmds)

    def open_process(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]":
        """Open a process for each command in pipeline and return the last one."""
        if not self._items:
            raise Exception("cannot open processes of empty pipeline.")
        procs: List[Popen[bytes]] = []
        for i, cmd in enumerate(self._items):
            stdin = procs[i - 1].stdout if i > 0 else stdin
            procs.append(cmd.open_process(stdin=stdin))
        for proc in procs[:-1]:
            proc.stdout.close() if proc.stdout else None
        return procs[-1]

    def __str__(self) -> str:
        return " | ".join(str(c) for c in self._items)


def cmd(*args: CmdArg) -> Cmd:
    """Return a command of program args."""
    return Cmd(args)


def pipe(*cmds: Cmd) -> Pipeline:
    """Return a pipeline of commands."""
    return Pipeline(cmds)


def run(
    cmd: Command[Any], timeout: Optional[float] = None
) -> "CompletedProcess[bytes]":
    """Run command and return the completed process."""
    proc = cmd.open_process()
    stdout, stderr = proc.communicate(timeout=timeout)
    return CompletedProcess(proc.args, proc.returncode, stdout, stderr)
