### piping
``` sh
ls | grep ...
```
``` python
pipe(cmd("ls"), cmd("grep", ...))
```

### process substitution
``` sh
diff <(zcat ... | sed ...) <(zcat ... | sed ...)
```
``` python
cmd(
    "diff",
    pipe(cmd("zcat", ...), cmd("sed", ...)),
    pipe(cmd("zcat", ...), cmd("sed", ...)),
)
```
