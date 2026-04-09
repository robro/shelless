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

import shlex
from abc import ABC, abstractmethod
from asyncio import wait_for
from asyncio.subprocess import Process, create_subprocess_exec
from dataclasses import dataclass  # pyright: ignore
from io import IOBase
from subprocess import CompletedProcess
from tempfile import NamedTemporaryFile, TemporaryFile
from typing import Any, IO, Iterable, List, Optional, TypeVar, Union, overload, Sequence

T = TypeVar("T")
_FILE = Union[IO[Any], int]


@dataclass
class ShellessProcess:
    """Wrapper process that holds temp file references for parent processes to use."""

    args: List[str]
    _process: Process
    _temp_files: List[IO[Any]]

    async def communicate(self, input: Optional[bytes] = None):
        return await self._process.communicate(input)

    @property
    def returncode(self):
        return self._process.returncode


class ShellessCommand(Sequence[T], ABC):
    """Abstract base class for runnable shell sequences."""

    _items: List[T]

    def __init__(self, items: Iterable[T]):
        self._items = list(items)

    @abstractmethod
    async def get_process(
        self,
        stdin: Optional[_FILE] = None,
        stdout: Optional[_FILE] = None,
        stderr: Optional[_FILE] = None,
        timeout: Optional[float] = None,
    ) -> ShellessProcess:
        pass

    def __len__(self) -> int:
        return len(self._items)

    @overload
    def __getitem__(self, index: int) -> T:
        pass

    @overload
    def __getitem__(self, index: slice) -> "ShellessCommand[T]":
        pass

    def __getitem__(self, index: Any) -> Union["ShellessCommand[T]", T]:
        if isinstance(index, int):
            return self._items[index]
        if isinstance(index, slice):
            return type(self)(self._items[index.start : index.stop : index.step])
        t_self = type(self).__name__
        t_index = type(index).__name__
        raise TypeError(f"{t_self} indices must be integers or slices, not {t_index}")

    def __add__(self, other: "ShellessCommand[T]") -> "ShellessCommand[T]":
        if isinstance(other, type(self)):
            return type(self)(self._items + other._items)
        t_self = type(self).__name__
        t_other = type(other).__name__
        raise TypeError(f'can only concatenate {t_self} (not "{t_other}") to {t_self}')

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join(item.__repr__() for item in self)})"


CmdArg = Union[ShellessCommand[Any], str]


class Cmd(ShellessCommand[CmdArg]):
    """Represents a single program command.

    Nested command arguments represent shell process substitution.
    """

    def __init__(self, args: Iterable[CmdArg]):
        super().__init__(args)

    async def get_process(
        self,
        stdin: Optional[_FILE] = None,
        stdout: Optional[_FILE] = None,
        stderr: Optional[_FILE] = None,
        timeout: Optional[float] = None,
    ) -> ShellessProcess:
        """Return process for this command after running all sub-commands."""
        args: List[str] = []
        temp_files: List[IO[bytes]] = []
        for arg in self:
            if isinstance(arg, ShellessCommand):
                temp_file = NamedTemporaryFile()
                process = await arg.get_process(None, temp_file, stderr, timeout)
                await wait_for(process.communicate(), timeout)
                temp_file.seek(0)
                temp_files.append(temp_file)
                args.append(temp_file.name)
            else:
                args.append(arg)
        process = await create_subprocess_exec(
            *args,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )
        return ShellessProcess(args, process, temp_files)

    def __str__(self) -> str:
        return " ".join(
            shlex.quote(arg) if isinstance(arg, str) else f"<({arg})" for arg in self
        )


class Pipeline(ShellessCommand[Cmd]):
    """Represents a chain of piped program commands."""

    def __init__(self, cmds: Iterable[Cmd]):
        super().__init__(cmds)

    async def get_process(
        self,
        stdin: Optional[_FILE] = None,
        stdout: Optional[_FILE] = None,
        stderr: Optional[_FILE] = None,
        timeout: Optional[float] = None,
    ) -> ShellessProcess:
        """Return process for last command in pipeline after running previous commands."""
        temp_file_1 = TemporaryFile()
        temp_file_2 = TemporaryFile()
        last_index = len(self) - 1
        for i, cmd in enumerate(self):
            stdin_ = stdin if i == 0 else temp_file_1
            stdout_ = stdout if i == last_index else temp_file_2
            process = await cmd.get_process(stdin_, stdout_, stderr, timeout)
            if i == last_index:
                return process
            await wait_for(process.communicate(), timeout)
            stdin_.seek(0) if isinstance(stdin_, IOBase) else None
            stdout_.seek(0) if isinstance(stdout_, IOBase) else None
            temp_file_1, temp_file_2 = temp_file_2, temp_file_1
        raise Exception(f"{type(self).__name__} requires at least 1 command to run")

    def __str__(self) -> str:
        return " | ".join(str(cmd) for cmd in self)


def cmd(*args: CmdArg) -> Cmd:
    """Return a command of program args."""
    return Cmd(args)


def pipe(*cmds: Cmd) -> Pipeline:
    """Return a pipeline of commands."""
    return Pipeline(cmds)


async def run(
    cmd: ShellessCommand[Any],
    stdin: Optional[_FILE] = None,
    stdout: Optional[_FILE] = None,
    stderr: Optional[_FILE] = None,
    input: Optional[bytes] = None,
    timeout: Optional[float] = None,
) -> "CompletedProcess[bytes]":
    """Run command and return the completed process."""
    process = await cmd.get_process(stdin, stdout, stderr, timeout)
    stdout_, stderr_ = await wait_for(process.communicate(input), timeout)
    assert process.returncode is not None
    return CompletedProcess(process.args, process.returncode, stdout_, stderr_)
