# shelless
```
Chain and nest shell commands without the shell

Pipeline(Cmd("sed", ...), Cmd("grep", ...))
$ sed ... | grep ...

Cmd("diff", Cmd("unzip", ...), Pipeline(Cmd("unzip", ...), Cmd("sed", ...)))
$ diff <(unzip ...) <(unzip ... | sed ...)
```
