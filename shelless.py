"""Chain and nest shell commands without the shell

cmd("sed", ...).pipe("grep", ...)
$ sed ... | grep ...

cmd("diff", cmd("unzip", ...), cmd("unzip", ...).pipe("sed", ...))
$ diff <(unzip ...) <(unzip ... | sed ...)
"""

from abc import ABC, abstractmethod
from subprocess import CompletedProcess, Popen, PIPE
from typing import IO, List, Optional, Union


class Shelless(ABC):
    """Abstract base class for objects that represent shell functionality."""

    @abstractmethod
    def run(self) -> "CompletedProcess[bytes]": ...

    @abstractmethod
    def pipe(self) -> "Pipeline": ...

    @abstractmethod
    def popen(self) -> "Popen[bytes]": ...

    @abstractmethod
    def get_cmds(self) -> List["Cmd"]: ...

    @abstractmethod
    def __str__(self) -> str: ...


class Cmd(Shelless):
    """Represents a shell command.

    Nested commands or pipelines represent shell process substitution.
    """

    args: List[Union[Shelless, str]]

    def __init__(self, *args: Union[Shelless, str]) -> None:
        self.args = list(args)

    def pipe(self, *args: Union[Shelless, str]) -> "Pipeline":
        """Create a pipe from this command to another command
        and return them as a pipeline."""
        return Pipeline(self, Cmd(*args))

    def run(self, timeout: Optional[float] = None) -> "CompletedProcess[bytes]":
        """Run command and return a CompletedProcess."""
        proc = self.popen()
        stdout, stderr = proc.communicate(timeout=timeout)
        return CompletedProcess(proc.args, proc.returncode, stdout, stderr)

    def popen(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]":
        """Return an opened process for this command."""
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

    def __str__(self) -> str:
        return " ".join(a if isinstance(a, str) else f"<({a})" for a in self.args)


class Pipeline(Shelless):
    """Represents piped shell commands.

    Contains list of command instances to pipe together.
    """

    cmds: List[Cmd]

    def __init__(self, *args: Shelless) -> None:
        self.cmds = sum([arg.get_cmds() for arg in args], [])  # pyright: ignore

    def pipe(self, *args: Union[Shelless, str]) -> "Pipeline":
        """Create a pipe from this pipeline to a command and return them
        as a new pipeline."""
        return Pipeline(self, Cmd(*args))

    def run(self, timeout: Optional[float] = None) -> "CompletedProcess[bytes]":
        """Run this pipeline's commands and return a completed process."""
        proc = self.popen()
        stdout, stderr = proc.communicate(timeout=timeout)
        return CompletedProcess(proc.args, proc.returncode, stdout, stderr)

    def popen(self) -> "Popen[bytes]":
        """Open a process for each of this pipeline's commands and return
        the final process."""
        procs: List[Popen[bytes]] = []
        for i, cmd in enumerate(self.cmds):
            stdin = procs[i - 1].stdout if i > 0 else None
            procs.append(cmd.popen(stdin))

        for proc in procs[:-1]:
            proc.stdout.close() if proc.stdout else None
        return procs[-1]

    def get_cmds(self) -> List[Cmd]:
        return self.cmds

    def __str__(self) -> str:
        return " | ".join(str(c) for c in self.cmds)


def cmd(*args: Union[Shelless, str]) -> Cmd:
    return Cmd(*args)
