"""Shell commands without the shell

$ ls | grep ...

run(line(cmd("ls"), cmd("grep", ...)))


$ diff <(unzip ... | sed ...) <(unzip ... | sed ...)

run(
    cmd(
        "diff",
        line(cmd("unzip", ...), cmd("sed", ...)),
        line(cmd("unzip", ...), cmd("sed", ...)),
    )
)
"""

from abc import ABC, abstractmethod
from subprocess import CompletedProcess, Popen, PIPE
from typing import IO, Iterable, List, Optional, Union


class Command(ABC):
    """Abstract base class for an object that represents a shell command."""

    @abstractmethod
    def popen(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]": ...

    @abstractmethod
    def get_cmds(self) -> List["Cmd"]: ...


CmdArg = Union[Command, str]


class Cmd(Command):
    """Represents a single program command.

    Nested commands represent shell process substitution.
    """

    args: List[CmdArg]

    def __init__(self, args: Iterable[CmdArg]) -> None:
        self.args = list(args)

    def popen(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]":
        """Open a process for this command and return it."""
        fds: List[int] = []
        args: List[str] = []
        procs: List[Popen[bytes]] = []
        for arg in self.args:
            if isinstance(arg, str):
                args.append(arg)
            else:
                proc = arg.popen()
                fd = proc.stdout.fileno() if proc.stdout else -1
                fds.append(fd)
                args.append(f"/dev/fd/{fd}")
                procs.append(proc)

        process = Popen(args, stdin=stdin, stdout=PIPE, stderr=PIPE, pass_fds=fds)
        for proc in procs:
            proc.stdout.close() if proc.stdout else None
        return process

    def get_cmds(self) -> List["Cmd"]:
        return [self]

    def __repr__(self) -> str:
        return f"Cmd({', '.join(a.__repr__() for a in self.args)})"

    def __str__(self) -> str:
        return " ".join(a if isinstance(a, str) else f"<({a})" for a in self.args)


class Pipeline(Command):
    """Represents a chain of piped program commands."""

    cmds: List[Cmd]

    def __init__(self, cmds: Iterable[Command]) -> None:
        self.cmds = sum([c.get_cmds() for c in cmds], [])  # pyright: ignore

    def popen(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]":
        """Open a process for each command in pipeline and return the last one."""
        procs: List[Popen[bytes]] = []
        for i, cmd in enumerate(self.cmds):
            stdin = procs[i - 1].stdout if i > 0 else stdin
            procs.append(cmd.popen(stdin=stdin))

        for proc in procs[:-1]:
            proc.stdout.close() if proc.stdout else None
        return procs[-1]

    def get_cmds(self) -> List["Cmd"]:
        return self.cmds

    def __repr__(self) -> str:
        return f"Pipeline({', '.join(c.__repr__() for c in self.cmds)})"

    def __str__(self) -> str:
        return " | ".join(str(c) for c in self.cmds)


def cmd(*args: CmdArg) -> Cmd:
    """Return a command for program with args."""
    return Cmd(args)


def line(*cmds: Command) -> Pipeline:
    """Return a pipeline of commands."""
    return Pipeline(cmds)


def run(cmd: Command, timeout: Optional[float] = None) -> "CompletedProcess[bytes]":
    """Run commands as pipeline and return the completed process."""
    proc = cmd.popen()
    stdout, stderr = proc.communicate(timeout=timeout)
    return CompletedProcess(proc.args, proc.returncode, stdout, stderr)
