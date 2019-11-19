- [ ] implement `local`
- [ ] capture stdout + stderr (local)
- [x] `remote`
- [x] capture stdout + stderr (remote)
- [ ] implement remote_file_exists
- [ ] implement `put`
- [ ] implement `get`
- [ ] use the `hosts` in the environment to determine `param_key` and `param_values` parameters to `execute`
- [ ] implement 'abort_on_prompts', bails when input on stdin is requested
- [ ] implement 'abort_exception', the exception to raise when execution is aborted
- [ ] implement `disconnect_all` that closes all open client connections


investigate:

* buildercore.core.stack_conn
    - and how it fits into the new reigme
* sharing open ssh session
    - I do believe the connection is closed after the command is run
* env `clean_revert`
* env `linewise`
    - used in `get`
    - not used explicitly in builder
    - prints contents per-line rather than per-chunk-of-bytes
* env `all_hosts` - list
* env `host` - single value, probably one of `all_hosts`
    - `param_list: all_hosts, param_key: host`
* env `parallel` - does the presence of this automatically do something in parallel??
* env `command` - this is *not* the `command` passed to `remote`. present in env when calling `exists`
* env 

ignored:

* env `capture`
