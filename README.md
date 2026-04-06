# shelless

``` python
shell features without the shell

piping:

$ ls | grep ...

run(pipe(cmd("ls"), cmd("grep", ...)))


process substitution:

$ diff <(unzip ... | sed ...) <(unzip ... | sed ...)

run(
    cmd(
        "diff",
        pipe(cmd("unzip", ...), cmd("sed", ...)),
        pipe(cmd("unzip", ...), cmd("sed", ...)),
    )
)
```
