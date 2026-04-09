### piping
``` sh
ls | grep ...
```
``` python
run([['ls'], ['grep', ...]])
```

### process substitution
``` sh
diff <(zcat ... | sed ...) <(zcat ... | sed ...)
```
``` python
sub1 = [['zcat', ...], ['sed', ...]]
sub2 = [['zcat', ...], ['sed', ...]]
run(['diff', sub1, sub2])
```
