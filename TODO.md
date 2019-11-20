- [x] implement `local`
- [x] capture stdout + stderr (local)
- [x] `remote`
- [x] capture stdout + stderr (remote)
- [x] implement remote_file_exists
- [ ] implement `put`
- [ ] implement `get`
- [ ] implement `lcd`
- [ ] implement `rcd`
- [x] use the `hosts` in the environment to determine `param_key` and `param_values` parameters to `execute`
- [ ] implement 'abort_on_prompts', bails when input on stdin is requested
- [ ] implement 'abort_exception', the exception to raise when execution is aborted
- [ ] implement `disconnect_all` that closes all open client connections
- [ ] implement ssh session sharing so multiple commands can be run

regression:

* builder 'cmd' running a task in parallel is hanging
    - used to work
    - no traceback

investigate:

* pssh is emitting log lines:
    - `INFO - pssh.host_logger - [34.201.187.7]	hello`
    - for `./bldr cmd:observer--prod,'echo hello',concurrency=serial`

* env `linewise`
    - used in `get`
    - used in `_execute` with parallel worker functions as well
        - I guess this would be useful to force if multiple processes are writing to your stdout?
    - not used explicitly in builder
    - prints contents per-line rather than per-chunk-of-bytes

* env `capture`
    - used only with `local` because it behaves differently to `remote`
        - you can't have both streaming output and captured output, apparently
        - when capture=True, the `ssh` command appears to hang because the output is being captured, which makes sense
            - may be a solution here, but not in scope for this project
    - implemented

ignored:

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

