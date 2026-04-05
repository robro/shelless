# shelless
```
Chain and nest shell commands without the shell

cmd("sed", ...).pipe("grep", ...)
$ sed ... | grep ...

cmd("diff", cmd("unzip", ...), cmd("unzip", ...).pipe("sed", ...))
$ diff <(unzip ...) <(unzip ... | sed ...)
```
