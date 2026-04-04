"""Chain and nest shell commands without the shell

Pipeline(Cmd("sed", ...), Cmd("grep", ...))
$ sed ... | grep ...

Cmd("diff", Cmd("unzip", ...), Pipeline(Cmd("unzip", ...), Cmd("sed", ...)))
$ diff <(unzip ...) <(unzip ... | sed ...)
"""

from abc import ABC, abstractmethod
from subprocess import CompletedProcess, Popen, PIPE
from typing import IO, List, Optional, Union


class Shelless(ABC):
    """Abstract base class for objects that represent shell functionality."""

    def run(self, timeout: Optional[float] = None) -> "CompletedProcess[bytes]":
        proc = self.popen()
        stdout, stderr = proc.communicate(timeout=timeout)
        return CompletedProcess(proc.args, proc.returncode, stdout, stderr)

    @abstractmethod
    def popen(self) -> "Popen[bytes]": ...

    @abstractmethod
    def __str__(self) -> str: ...


CmdArg = Union[str, "Cmd", "Pipeline"]
PipelineArg = Union["Cmd", "Pipeline"]


class Cmd(Shelless):
    """Represents a shell command.

    Takes any combination of strings, Cmds, and Pipelines as args.

    Nested Cmds or Pipelines represent shell process substitution.
    """

    args: List[CmdArg]

    def __init__(self, *args: CmdArg) -> None:
        self.args = list(args)

    def run(self, timeout: Optional[float] = None) -> "CompletedProcess[bytes]":
        """Run this Cmd and return a CompletedProcess."""
        return super().run(timeout)

    def popen(self, stdin: Optional[IO[bytes]] = None) -> "Popen[bytes]":
        """Return an opened process for this Cmd.

        Also opens subprocesses for any nested Cmds or Pipelines.
        """
        fds: List[int] = []
        args: List[str] = []
        procs: List[Popen[bytes]] = []
        for arg in self.args:
            if isinstance(arg, str):
                args.append(arg)
            else:
                _proc = arg.popen()
                fd = _proc.stdout.fileno() if _proc.stdout else -1
                fds.append(fd)
                args.append(f"/dev/fd/{fd}")
                procs.append(_proc)

        proc = Popen(args, stdin=stdin, stdout=PIPE, stderr=PIPE, pass_fds=fds)
        for _proc in filter(_has_stdout, procs):
            _proc.stdout.close()  # pyright: ignore
        return proc

    def __str__(self) -> str:
        return " ".join(a if isinstance(a, str) else f"<({a})" for a in self.args)


class Pipeline(Shelless):
    """Represents piping of shell commands.

    Takes any combination of Cmds and Pipelines as args.
    """

    cmds: List[Cmd]

    def __init__(self, *args: PipelineArg) -> None:
        self.cmds = []
        for arg in args:
            if isinstance(arg, Cmd):
                self.cmds.append(arg)
            else:
                self.cmds.extend(arg.cmds)

    def run(self, timeout: Optional[float] = None) -> "CompletedProcess[bytes]":
        """Run this Pipeline and return a CompletedProcess."""
        return super().run(timeout)

    def popen(self) -> "Popen[bytes]":
        """Return an opened process for the last Cmd in this Pipeline.

        Opens a process for each subcommand and pipes each process's stdout into
        the stdin of the following process.
        """
        procs: List[Popen[bytes]] = []
        for i, cmd in enumerate(self.cmds):
            stdin = procs[i - 1].stdout if i > 0 else None
            procs.append(cmd.popen(stdin))

        for proc in filter(_has_stdout, procs[:-1]):
            proc.stdout.close()  # pyright: ignore
        return procs[-1]

    def __str__(self) -> str:
        return " | ".join(str(c) for c in self.cmds)


def _has_stdout(proc: "Popen[bytes]") -> bool:
    return proc.stdout is not None
