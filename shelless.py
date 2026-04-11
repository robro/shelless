"""shell features without 'shell=True'


piping:

ls | grep ...

run([['ls'], ['grep', ...]])


process substitution:

diff <(zcat ... | sed ...) <(zcat ... | sed ...)

sub1 = [['zcat', ...], ['sed', ...]]
sub2 = [['zcat', ...], ['sed', ...]]
run(['diff', sub1, sub2])
"""

import shlex
from dataclasses import dataclass  # pyright: ignore
from io import IOBase
from subprocess import CompletedProcess, Popen
from tempfile import NamedTemporaryFile, TemporaryFile
from typing import Any, IO, List, Optional, Union, Sequence

_FILE = Union[IO[Any], int]
_CMD = Sequence[Union[str, "_CMD"]]
_PIPELINE = Sequence[_CMD]


@dataclass
class ShellessProcess:
    """Wrapper process that holds temp file references for parent processes to use."""

    _process: "Popen[bytes]"
    _temp_files: List[IO[Any]]

    def communicate(
        self, input: Optional[bytes] = None, timeout: Optional[float] = None
    ):
        return self._process.communicate(input, timeout)

    @property
    def args(self):
        return self._process.args

    @property
    def returncode(self):
        return self._process.returncode


def run(
    cmd: _CMD,
    stdin: Optional[_FILE] = None,
    stdout: Optional[_FILE] = None,
    stderr: Optional[_FILE] = None,
    input: Optional[bytes] = None,
    timeout: Optional[float] = None,
) -> "CompletedProcess[bytes]":
    """Run command and return the completed process."""
    process = _get_proc(cmd, stdin, stdout, stderr, timeout)
    stdout_, stderr_ = process.communicate(input, timeout)
    return CompletedProcess(process.args, process.returncode, stdout_, stderr_)


def _get_proc(
    cmd: _CMD,
    stdin: Optional[_FILE] = None,
    stdout: Optional[_FILE] = None,
    stderr: Optional[_FILE] = None,
    timeout: Optional[float] = None,
):
    func = _get_cmd_proc if isinstance(cmd[0], str) else _get_pipe_proc
    return func(cmd, stdin, stdout, stderr, timeout)


def _get_cmd_proc(
    cmd: _CMD,
    stdin: Optional[_FILE] = None,
    stdout: Optional[_FILE] = None,
    stderr: Optional[_FILE] = None,
    timeout: Optional[float] = None,
) -> ShellessProcess:
    """Return process for command after running all sub-commands."""
    args: List[str] = []
    temp_files: List[IO[bytes]] = []
    for arg in cmd:
        if isinstance(arg, str):
            args.append(arg)
        else:
            temp_file = NamedTemporaryFile()
            process = _get_proc(arg, None, temp_file, stderr, timeout)
            process.communicate(timeout=timeout)
            temp_file.seek(0)
            temp_files.append(temp_file)
            args.append(temp_file.name)
    process = Popen(args, stdin=stdin, stdout=stdout, stderr=stderr)
    return ShellessProcess(process, temp_files)


def _get_pipe_proc(
    pipeline: _PIPELINE,
    stdin: Optional[_FILE] = None,
    stdout: Optional[_FILE] = None,
    stderr: Optional[_FILE] = None,
    timeout: Optional[float] = None,
) -> ShellessProcess:
    """Return process for last command in pipeline after running previous commands."""
    temp_file_1 = TemporaryFile()
    temp_file_2 = TemporaryFile()
    last_index = len(pipeline) - 1
    for i, cmd in enumerate(pipeline):
        stdin_ = stdin if i == 0 else temp_file_1
        stdout_ = stdout if i == last_index else temp_file_2
        process = _get_cmd_proc(cmd, stdin_, stdout_, stderr, timeout)
        if i == last_index:
            return process
        process.communicate(timeout=timeout)
        stdin_.seek(0) if isinstance(stdin_, IOBase) else None
        stdout_.seek(0) if isinstance(stdout_, IOBase) else None
        temp_file_1, temp_file_2 = temp_file_2, temp_file_1
    raise Exception(f"pipeline requires at least 1 command to run")


def shell(cmd: _CMD) -> str:
    """Return shell representation of command as a string."""
    func = _cmdstr if isinstance(cmd[0], str) else _pipestr
    return func(cmd)


def _cmdstr(cmd: _CMD) -> str:
    args = [shlex.quote(a) if isinstance(a, str) else f"<({shell(a)})" for a in cmd]
    return " ".join(args)


def _pipestr(pipeline: _PIPELINE) -> str:
    cmd = [shell(cmd) for cmd in pipeline]
    return " | ".join(cmd)
