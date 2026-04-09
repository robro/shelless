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
from asyncio import wait_for
from asyncio.subprocess import Process, create_subprocess_exec
from dataclasses import dataclass  # pyright: ignore
from io import IOBase
from subprocess import CompletedProcess
from tempfile import NamedTemporaryFile, TemporaryFile
from typing import Any, IO, List, Optional, Union, Sequence

_FILE = Union[IO[Any], int]
_CMD = Sequence[Union[str, "_CMD"]]
_PIPELINE = Sequence[_CMD]


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


async def run(
    cmd: _CMD,
    stdin: Optional[_FILE] = None,
    stdout: Optional[_FILE] = None,
    stderr: Optional[_FILE] = None,
    input: Optional[bytes] = None,
    timeout: Optional[float] = None,
) -> "CompletedProcess[bytes]":
    """Run command and return the completed process."""
    process = await _get_proc(cmd, stdin, stdout, stderr, timeout)
    stdout_, stderr_ = await wait_for(process.communicate(input), timeout)
    assert process.returncode is not None
    return CompletedProcess(process.args, process.returncode, stdout_, stderr_)


async def _get_proc(
    cmd: _CMD,
    stdin: Optional[_FILE] = None,
    stdout: Optional[_FILE] = None,
    stderr: Optional[_FILE] = None,
    timeout: Optional[float] = None,
):
    func = _get_cmd_proc if isinstance(cmd[0], str) else _get_pipe_proc
    return await func(cmd, stdin, stdout, stderr, timeout)


async def _get_cmd_proc(
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
            process = await _get_proc(arg, None, temp_file, stderr, timeout)
            await wait_for(process.communicate(), timeout)
            temp_file.seek(0)
            temp_files.append(temp_file)
            args.append(temp_file.name)
    process = await create_subprocess_exec(
        *args,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )
    return ShellessProcess(args, process, temp_files)


async def _get_pipe_proc(
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
        process = await _get_cmd_proc(cmd, stdin_, stdout_, stderr, timeout)
        if i == last_index:
            return process
        await wait_for(process.communicate(), timeout)
        stdin_.seek(0) if isinstance(stdin_, IOBase) else None
        stdout_.seek(0) if isinstance(stdout_, IOBase) else None
        temp_file_1, temp_file_2 = temp_file_2, temp_file_1
    raise Exception(f"pipeline requires at least 1 command to run")


def shell(cmd: _CMD) -> str:
    func = _cmdstr if isinstance(cmd[0], str) else _pipestr
    return func(cmd)


def _cmdstr(cmd: _CMD) -> str:
    args: List[str] = []
    for arg in cmd:
        if isinstance(arg, str):
            args.append(shlex.quote(arg))
        else:
            func = _cmdstr if isinstance(arg[0], str) else _pipestr
            args.append(f"<({func(arg)})")
    return " ".join(args)


def _pipestr(pipe: _PIPELINE) -> str:
    cmds: List[str] = []
    for cmd in pipe:
        func = _cmdstr if isinstance(cmd[0], str) else _pipestr
        cmds.append(func(cmd))
    return " | ".join(cmds)
