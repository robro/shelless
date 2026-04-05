"""Chain and nest shell commands without the shell

$ ls ... | grep ...

run(pln(cmd("ls", ...), cmd("grep", ...)))  [fp  style]
Cmd("ls", ...).pipe(Cmd("grep", ...)).run() [oop style]

$ diff <(unzip ... | sed ...) <(unzip ... | sed ...)

Cmd(
    "diff",
    Cmd("unzip", ...).pipe(Cmd("sed", ...)),
    Cmd("unzip", ...).pipe(Cmd("sed", ...)),
).run()
[oop style]

run(
    cmd(
        "diff",
        pln(cmd("unzip", ...), cmd("sed", ...)),
        pln(cmd("unzip", ...), cmd("sed", ...)),
    )
)
[fp style]
"""

from abc import ABC, abstractmethod
from subprocess import CompletedProcess, Popen, PIPE
from typing import IO, List, Optional, Union


class Command(ABC):
    """Abstract base class for objects that represent shell functionality."""

    @abstractmethod
    def popen(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]": ...

    @abstractmethod
    def run(self, timeout: Optional[float] = None) -> CompletedProcess[bytes]: ...

    @abstractmethod
    def pipe(self, cmd: "Command") -> "Pipeline": ...

    @abstractmethod
    def get_cmds(self) -> List["Cmd"]: ...

    @abstractmethod
    def __str__(self) -> str: ...


CmdArgs = Union[Command, str]


class Cmd(Command):
    """Represents a single program command.

    Nested commands represent shell process substitution.
    """

    prog: str
    args: List[CmdArgs]

    def __init__(self, prog: str, *args: CmdArgs) -> None:
        self.prog = prog
        self.args = list(args)

    def popen(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]":
        """Open a process for this command and return it."""
        fds: List[int] = []
        args = [self.prog]
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

    def run(self, timeout: Optional[float] = None) -> CompletedProcess[bytes]:
        """Run command and return the completed process."""
        proc = self.popen()
        stdout, stderr = proc.communicate(timeout=timeout)
        return CompletedProcess(proc.args, proc.returncode, stdout, stderr)

    def pipe(self, cmd: Command) -> "Pipeline":
        """Return a new pipeline from this command to command."""
        return Pipeline(self, cmd)

    def get_cmds(self) -> List["Cmd"]:
        """Return all commands this command contains."""
        return [self]

    def __str__(self) -> str:
        args = " ".join(a if isinstance(a, str) else f"<({a})" for a in self.args)
        return f"{self.prog} {args}"


class Pipeline(Command):
    """Represents an output-->input chain of program commands."""

    cmds: List["Cmd"]

    def __init__(self, *cmds: Command) -> None:
        self.cmds = []
        for cmd in cmds:
            self.cmds.extend(Cmd(c.prog, *c.args) for c in cmd.get_cmds())

    def popen(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]":
        """
        Open a process for each of this pipeline's commands and return
        the final process.
        """
        procs: List[Popen[bytes]] = []
        for i, cmd in enumerate(self.cmds):
            stdin = procs[i - 1].stdout if i > 0 else stdin
            procs.append(cmd.popen(stdin=stdin))

        for proc in procs[:-1]:
            proc.stdout.close() if proc.stdout else None
        return procs[-1]

    def run(self, timeout: Optional[float] = None) -> CompletedProcess[bytes]:
        """Run pipeline and return the completed process."""
        proc = self.popen()
        stdout, stderr = proc.communicate(timeout=timeout)
        return CompletedProcess(proc.args, proc.returncode, stdout, stderr)

    def pipe(self, cmd: Command) -> "Pipeline":
        """Return a new pipeline from this pipeline to command."""
        return Pipeline(self, cmd)

    def get_cmds(self) -> List["Cmd"]:
        """Return all commands this pipeline contains."""
        return self.cmds

    def __str__(self) -> str:
        return " | ".join(str(c) for c in self.cmds)


def cmd(program: str, *args: CmdArgs) -> Cmd:
    """Return a command for program with args."""
    return Cmd(program, *args)


def pln(*cmds: Command) -> Pipeline:
    """Return a pipeline of commands."""
    return Pipeline(*cmds)


def run(cmd: Command, timeout: Optional[float] = None) -> CompletedProcess[bytes]:
    """Run command and return the completed process."""
    proc = cmd.popen()
    stdout, stderr = proc.communicate(timeout=timeout)
    return CompletedProcess(proc.args, proc.returncode, stdout, stderr)
