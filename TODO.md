# TODO for 0.1.0 release

- [x] implement `local`
- [x] capture stdout + stderr (local)
- [x] `remote`
- [x] capture stdout + stderr (remote)
- [x] implement remote_file_exists
- [x] implement `put`/`upload`
- [x] implement `put`/`upload` 'use_sudo' hack
- [x] implement `put`/`upload` from bytes buffer
- [x] implement `get`/`download`
- [x] implement `get`/`download` 'use_sudo' hack
- [x] implement `get`/`download` to bytes buffer
- [x] implement `lcd`
- [x] implement `rcd`
- [x] use the `hosts` in the environment to determine `param_key` and `param_values` parameters to `execute`
- [x] implement 'timeout'
- [x] implement 'abort_on_prompts', bails when ~input on stdin is requested~ *Fabric* issues a prompt
- [x] implement 'abort_exception', the exception to raise when execution is aborted
- [x] implement some kind of 'initial_settings' hook for apps to set their own defaults
- [x] remove local scope support in 'settings' - it's unused and makes a complicated thing more so
- [x] implement 'warn_only', "warn, instead of abort, when commands fail", used in masterless when updating repos
- [x] implement `quiet=True` in `local` and `remote`
- [x] implement ssh session sharing so multiple commands can be run
- [x] output is being duplicated, once from logging, once from us. what does builder do?
- [x] separate development dependencies from required ones
- [x] test against local sshd server
- [x] test automation
- [x] python 2 tests
- [x] python 3 tests
- [x] integrate with builder
- [x] convert example.py to a proper test suite
- [x] linting
- [x] coverage

## TODO bucket

- [ ] move taskrunner from builder into threadbare, including tests
- [ ] SFTP is excrutiatingly slow. Can we switch to SCP?
    - This is not a Fabric/Threadbare/Paramiko/ParallelSSH problem but a SSH/SFTP problem.

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
            - it would be like a database's ATOM guarantees were only guaranteed 'most' of the time.

