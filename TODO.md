- [x] implement `local`
- [x] capture stdout + stderr (local)
- [x] `remote`
- [x] capture stdout + stderr (remote)
- [x] implement remote_file_exists
- [x] implement `put`/`upload`
- [x] implement `put`/`upload` 'use_sudo' hack
- [x] implement `get`/`download`
- [x] implement `get`/`download` 'use_sudo' hack
- [ ] implement `lcd`
- [ ] implement `rcd`
- [x] use the `hosts` in the environment to determine `param_key` and `param_values` parameters to `execute`
- [ ] implement 'abort_on_prompts', bails when input on stdin is requested
- [ ] implement 'abort_exception', the exception to raise when execution is aborted
- [x] implement ssh session sharing so multiple commands can be run

investigate:

* SFTP (default for pssh and fabric) is excruciatingly slow
    - can we safely switch to SCP?

* pssh is emitting log lines:
    - `INFO - pssh.host_logger - [34.201.187.7]	hello`
    - for `./bldr cmd:observer--prod,'echo hello',concurrency=serial`

* env `linewise`
    - used in `get`
    - used in `_execute` with parallel worker functions as well
        - I guess this would be useful to force if multiple processes are writing to your stdout?
    - not used explicitly in builder
    - prints contents per-line rather than per-chunk-of-bytes

* are we using upload/download on directories of files? 
    - because Fabric and pssh totally support that.
        - they're both using SFTP under the hood

ignored:

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

