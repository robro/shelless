# shelless
### piping
```
$ ls ... | grep ...

Cmd("ls", ...).pipe(Cmd("grep", ...)).run() [oop style]

run(pln(cmd("ls", ...), cmd("grep", ...)))  [fp style]
```
### process substitution
```
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
```
