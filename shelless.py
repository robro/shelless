"""shell features without 'shell=True'


piping:

ls | grep ...

run(pipe(cmd("ls"), cmd("grep", ...)))


process substitution:

diff <(unzip ... | sed ...) <(unzip ... | sed ...)

run(
    cmd(
        "diff",
        pipe(cmd("unzip", ...), cmd("sed", ...)),
        pipe(cmd("unzip", ...), cmd("sed", ...)),
    )
)
"""

from abc import ABC, abstractmethod
from subprocess import CompletedProcess, Popen, PIPE
from typing import Any, IO, Iterable, List, Optional, TypeVar, Union, overload
from typing import Sequence

T = TypeVar("T")


class Command(Sequence[T], ABC):
    """Abstract base class for runnable shell sequences."""

    _items: List[T]

    def __init__(self, items: Iterable[T]):
        self._items = list(items)

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
        self_type = type(self).__name__
        index_type = type(index).__name__
        raise TypeError(
            f"{self_type} indices must be integers or slices, not {index_type}"
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join(x.__repr__() for x in self._items)})"


CmdArg = Union[Command[Any], str]


class Cmd(Command[CmdArg]):
    """Represents a single program command.

    Nested commands represent shell process substitution.
    """

    def open_process(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]":
        """Open a process for this command and return it."""
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

    def open_process(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]":
        """Open a process for each command in pipeline and return the last one."""
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
