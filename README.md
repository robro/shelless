# shell features without `shell=True`

### piping
```
$ ls | grep ...
```
``` python
>>> run(pipe(cmd("ls"), cmd("grep", ...)))
```

### process substitution
```
$ diff <(unzip ... | sed ...) <(unzip ... | sed ...)
```
``` python
run(
    cmd(
        "diff",
        pipe(cmd("unzip", ...), cmd("sed", ...)),
        pipe(cmd("unzip", ...), cmd("sed", ...)),
    )
)
```
