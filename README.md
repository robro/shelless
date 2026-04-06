# shelless
### piping
```
$ ls | grep ...

run(line(cmd("ls"), cmd("grep", ...)))
```
### process substitution
```
$ diff <(unzip ... | sed ...) <(unzip ... | sed ...)

run(
    cmd(
        "diff",
        line(cmd("unzip", ...), cmd("sed", ...)),
        line(cmd("unzip", ...), cmd("sed", ...)),
    )
)
```
