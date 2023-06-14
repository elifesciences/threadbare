## TODO bucket

- [ ] move taskrunner from builder into threadbare, including tests

## investigate:

* with pssh logging disabled, ensure we have some means of prefixing output with IP addresses

* `abort_on_prompts=True`
    - https://github.com/mathiasertl/fabric/blob/19c9f3fcf22e384fe2a6127ea9c268a3a4ff8a6b/fabric/network.py#L446
    - you would think this would abort if a prompt was issued, which is *technically* correct, but only for certain 
    defintions of 'prompt'
    - it will abort if *Fabric* issues the prompt, but not if *you* issue a command that requires a prompt
        - for example, this will **not** abort:

```
    with settings(abort_on_prompts=True):
        local("read -p '> '")
```

* env `linewise`
    - used in `get`
    - used in `_execute` with parallel worker functions as well
        - I guess this would be useful to force if multiple processes are writing to your stdout?
    - not used explicitly in builder
    - prints contents per-line rather than per-chunk-of-bytes

## wontfix:

* are we using upload/download on directories of files? 
    - because Fabric and pssh totally support that.
        - they're both using SFTP under the hood

* implement `disconnect_all` that closes all open client connections
    - client connections are closed automatically when the context is left
        - I *think* Fabric handles these differently with it's `clean_revert` setting that would leave connections hanging around still open

* env `parallel` - does the presence of this automatically do something in parallel??
    - no, see: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L223-L227
    - it looks like it's only set in the environment for tasks running in parallel to let *them* know that they are running in parallel
    - ignoring for now

* env `clean_revert`
    - https://github.com/mathiasertl/fabric/blob/master/fabric/context_managers.py#L203-L233
    - this option looks like a *fucking mire* and we ought stay very clear of it
        - for one, it means the opposite. clean_revert=False would be more appropriate
        - for two, you're messing with an otherwise easily understood mechanism for temporarily messing with global state
            - it would be like a database's ACID guarantees were only guaranteed 'most' of the time.

