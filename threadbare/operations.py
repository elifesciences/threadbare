from functools import wraps, partial
from datetime import datetime
import tempfile
import contextlib
import subprocess
from threading import Timer
import getpass
import pssh.exceptions
import os, sys
from pssh.clients.native import SSHClient as PSSHClient
import gevent
import io
import logging
from . import state
from .common import (
    PromptedException,
    merge,
    subdict,
    rename,
    cwd,
    sudo_wrap_command,
    cwd_wrap_command,
    shell_wrap_command,
    ensure,
)


LOG = logging.getLogger(__name__)


class SSHClient(PSSHClient):
    def __deepcopy__(self, memo):
        # do not copy.deepcopy ourselves or the pssh SSHClient object, just
        # return a reference to the object (self)
        # - https://docs.python.org/3/library/copy.html
        return self


class NetworkError(Exception):
    "generic 'died while doing something network-related' catch-all exception class."
    pass


class WrappedNetworkError(NetworkError):
    "groups several exceptions into a single WrappedNetworkError"

    def __init__(self, exc):
        self.wrapped = exc


def pem_key():
    """returns the first private key found in a list of common private keys.
    if none of the keys exist, the default (first) key will be returned."""
    id_list = ["id_rsa", "id_dsa", "identity", "id_ecdsa"]
    id_list = [os.path.expanduser("~/.ssh/" + idstr) for idstr in id_list]
    for id_path in id_list:
        if os.path.isfile(id_path):
            return id_path
        LOG.debug("key not found: %s" % id_path)

    default = id_list[0]
    return default


def handle(base_kwargs, kwargs):
    """handles the merging of the base set of function keyword arguments and their possible overrides.
    `base_kwargs` is a map of the function's keyword arguments and their defaults.
    `kwargs` are the keyword arguments used when executing the function.

    the keys from `base_kwargs` are used to determine which keys to extract from the `kwargs` and any
    global settings.

    returns a triple of (`global_kwargs`, `user_kwargs`, `final_kwargs`) where
    `global_kwargs` is the subset of keyword arguments extracted from `state.env`,
    `user_kwargs` is the subset of keyword arguments extracted from the given kwargs and
    `final_kwargs` is the result of merging `base_kwargs` <- `global_kwargs` <- `user_kwargs`

    'user' keyword arguments that are explicitly passed in take precedence over all others and
    'global' keyword arguments take precedence over the function's defaults kwargs."""
    key_list = base_kwargs.keys()
    global_kwargs = subdict(state.ENV, key_list)
    user_kwargs = subdict(kwargs, key_list)
    final_kwargs = merge(base_kwargs, global_kwargs, user_kwargs)
    return global_kwargs, user_kwargs, final_kwargs


# api


@contextlib.contextmanager
def lcd(local_dir):
    "temporarily changes the local working directory"
    ensure(os.path.isdir(local_dir), "not a directory: %s" % local_dir)
    with state.settings():
        current_dir = cwd()
        state.add_cleanup(lambda: os.chdir(current_dir))
        os.chdir(local_dir)
        yield


@contextlib.contextmanager
def rcd(remote_working_dir):
    "ensures all commands run are done from the given remote directory. if remote directory doesn't exist, command will not be run"
    with state.settings(remote_working_dir=remote_working_dir):
        yield


@contextlib.contextmanager
def hide(what=None):
    "hides *all* output, regardless of `what` type of output is to be hidden."
    with state.settings(quiet=True):
        yield


def _ssh_default_settings():
    "default settings for dealing with ssh."
    return {
        # current user. sensible default but probably not what you want
        "user": getpass.getuser(),
        "host_string": None,
        # looks for the same ~4 possible keys as Fabric and ParallelSSH.
        # uses the first one it finds or the most common if none found.
        "key_filename": pem_key(),
        "port": 22,
        "use_shell": True,
        "use_sudo": False,
        "combine_stderr": True,
        "quiet": False,
        "remote_working_dir": None,
        "timeout": None,
        "warn_only": False,  # https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L301-L305
        "abort_exception": RuntimeError,
    }


def _ssh_client(**kwargs):
    """returns an instance of pssh.clients.native.SSHClient
    if within a state context, looks for a client already in use and returns that if found.
    if not found, creates a new one and stores it for later use."""

    # parameters we're interested in and their default values
    base_kwargs = subdict(
        _ssh_default_settings(), ["user", "host_string", "key_filename", "port"]
    )
    global_kwargs, user_kwargs, final_kwargs = handle(base_kwargs, kwargs)
    final_kwargs["password"] = None  # always private keys
    rename(final_kwargs, [("key_filename", "pkey"), ("host_string", "host")])

    # if we're not using global state, return the new client as-is
    env = state.ENV
    if env.read_only:
        return SSHClient(**final_kwargs)

    client_map_key = "ssh_client"
    client_key = subdict(final_kwargs, ["user", "host", "pkey", "port", "timeout"])
    client_key = tuple(sorted(client_key.items()))

    # otherwise, check to see if a previous client is available for this host
    client_map = env.get(client_map_key, {})
    if client_key in client_map:
        return client_map[client_key]

    # if not, create a new one and store it in the state

    # https://parallel-ssh.readthedocs.io/en/latest/native_single.html#pssh.clients.native.single.SSHClient
    client = SSHClient(**final_kwargs)

    # disconnect session when leaving context manager
    state.add_cleanup(lambda: client.disconnect())

    client_map[client_key] = client
    env[client_map_key] = client_map

    return client


def _execute(command, user, key_filename, host_string, port, use_pty, timeout):
    """creates an SSHClient object and executes given `command` with the given parameters."""
    client = _ssh_client(
        user=user, host_string=host_string, key_filename=key_filename, port=port
    )

    shell = False  # handled ourselves
    sudo = False  # handled ourselves
    user = None  # user to sudo to
    encoding = "utf-8"  # used everywhere

    # https://parallel-ssh.readthedocs.io/en/latest/native_single.html#pssh.clients.native.single.SSHClient.run_command
    # https://github.com/ParallelSSH/parallel-ssh/blob/master/pssh/output.py
    host_output = client.run_command(
        command, sudo, user, use_pty, shell, encoding, timeout
    )

    host_string = host_output.host
    stdout = host_output.stdout
    stderr = host_output.stderr

    def get_exit_code():
        client.wait_finished(host_output)
        return host_output.exit_code

    return {
        # defer executing as it consumes output entirely before returning. this
        # removes our chance to display/transform output as it is streamed to us
        "return_code": get_exit_code,
        "command": command,
        "stdout": stdout,
        "stderr": stderr,
    }


def _print_line(output_pipe, line, **kwargs):
    """writes the given `line` (string) to the given `output_pipe` (file-like object)
    if `quiet` is True, `line` is *not* written to `output_pipe`.
    if `discard_output` is True, `line` is *not* returned and output does *not* accumulate in memory.
    """

    base_kwargs = {
        "discard_output": False,
        "quiet": False,
        "line_template": "[{host}] {pipe}: {line}\n",  # "1.2.3.4  err: Foo not found\n"
        "display_prefix": True,  # strips everything in `line_template` before "{line}"
        "custom_pipe": None,
    }
    global_kwargs, user_kwargs, final_kwargs = handle(base_kwargs, kwargs)

    if not final_kwargs["quiet"]:
        # useful values that can be part of the template
        pipe_type = "err" if output_pipe == sys.stderr else "out"
        if final_kwargs["custom_pipe"]:
            pipe_type = final_kwargs["custom_pipe"]  # like "run"

        dt = datetime.now()
        template_kwargs = {
            "line": line,
            "year": dt.year,
            "month": dt.month,
            "day": dt.day,
            "hour": dt.hour,
            "minute": dt.minute,
            "second": dt.second,
            "ms": dt.microsecond,
            "host": state.ENV.get("host_string", ""),
            "pipe": pipe_type,
        }

        # render template and write to given pipe
        template = final_kwargs["line_template"]

        if not final_kwargs["display_prefix"]:
            try:
                template = template[template.index("{line}") :]
            except ValueError:  # "substring not found"
                msg = "'display_prefix' option ignored: '{line}' not found in 'line_template' setting"
                LOG.warning(msg)

        output_pipe.write(template.format(**template_kwargs))

    if not final_kwargs["discard_output"]:
        return line  # free of any formatting


def _process_output(output_pipe, result_buffer, **kwargs):
    "calls `_print_line` on each result in `result_list`."

    # always process the results as soon as we have them
    # use `quiet=True` to hide the printing of output to stdout/stderr
    # use `discard_output=True` to discard the results as soon as they are read.
    # `stderr` results may be empty if `combine_stderr` in call to `remote` was `True`
    new_results = [_print_line(output_pipe, line, **kwargs) for line in result_buffer]
    output_pipe.flush()
    if "discard_output" in kwargs and not kwargs["discard_output"]:
        return new_results


def _print_running(command, output_pipe, **kwargs):
    """Prints the command to be run on a line of output prior to executing a command.
    Obeys the formatting and rules of the context in which the command is being exected.
    Deprecated. This is to mimic Fabric's command output until we're sure nothing depends on it.
    It will be replaced with a standard LOG.info output eventually."""
    keepers = ["display_running", "quiet", "discard_output", "line_template"]
    kwargs = subdict(kwargs, keepers)
    if kwargs["display_running"]:
        if not isinstance(command, list):
            command = [command]
        command = " ".join(command)
        return _print_line(output_pipe, command, custom_pipe="run", **kwargs)


def abort(result, err_msg, **kwargs):
    """raises a `RuntimeError` with the given `err_msg` and the given `result` attached to it's `.result` property.
    issues a warning and returns the given `result` if `settings.warn_only` is `True`.
    raises a SystemExit with a return code of `1` if `settings.abort_exception` is set to None.
    """
    base_kwargs = {
        "quiet": False,
        "warn_only": False,
        "display_aborts": True,
        "abort_exception": RuntimeError,
    }
    global_kwargs, user_kwargs, final_kwargs = handle(base_kwargs, kwargs)

    if final_kwargs["warn_only"]:
        if not final_kwargs["quiet"]:
            LOG.warning(err_msg)
        return result

    if final_kwargs["display_aborts"]:
        if not final_kwargs["quiet"]:
            LOG.error("Fatal error: %s" % err_msg)

    abort_exc_klass = final_kwargs["abort_exception"]
    if abort_exc_klass:
        exc = abort_exc_klass(err_msg)
        setattr(exc, "result", result)
        raise exc

    # https://docs.python.org/3/library/exceptions.html#SystemExit
    # # https://github.com/mathiasertl/fabric/blob/master/fabric/utils.py#L30-L63
    exc = SystemExit(1)
    exc.message = err_msg
    raise exc


# https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L338
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L898-L901
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L975
def remote(command, **kwargs):
    "preprocesses given `command` and options before sending it to `_execute` to be executed on remote host"

    # Fabric function signature for `run`
    # shell=True # done
    # pty=True   # mutually exclusive with `combine_stderr` in pssh. not sure how Fabric/Paramiko is doing it
    # combine_stderr=None # mutually exclusive with use_pty. 'True' in global env.
    # quiet=False, # done
    # warn_only=False # done
    # stdout=None # done, stdout/stderr always available unless explicitly discarded. 'see discard_output'
    # stderr=None # done, stderr not available when combine_stderr is `True`
    # timeout=None # done
    # shell_escape=None # ignored. shell commands are always escaped
    # capture_buffer_size=None # correlates to `ssh2.channel.read` and the `size` parameter. Ignored.

    # parameters we're interested in and their default values
    base_kwargs = _ssh_default_settings()
    base_kwargs.update({"display_running": True, "discard_output": False})
    global_kwargs, user_kwargs, final_kwargs = handle(base_kwargs, kwargs)

    # wrap the command up
    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L920-L925
    if final_kwargs["remote_working_dir"]:
        command = cwd_wrap_command(command, final_kwargs["remote_working_dir"])
    if final_kwargs["use_shell"]:
        command = shell_wrap_command(command)
    if final_kwargs["use_sudo"]:
        command = sudo_wrap_command(command)

    # if use_pty is True, stdout and stderr are combined and stderr will yield nothing.
    # - https://parallel-ssh.readthedocs.io/en/latest/advanced.html#combined-stdout-stderr
    use_pty = final_kwargs["combine_stderr"]

    # values `remote` specifically passes to `_execute`
    execute_kwargs = {"command": command, "use_pty": use_pty}
    execute_kwargs = merge(final_kwargs, execute_kwargs)
    execute_kwargs = subdict(
        execute_kwargs,
        [
            "command",
            "user",
            "key_filename",
            "host_string",
            "port",
            "use_pty",
            "timeout",
        ],
    )

    # TODO: validate `_execute`s args. `host_string` can't be None for example

    # run command
    _print_running(command, sys.stdout, **final_kwargs)
    result = _execute(**execute_kwargs)

    # handle stdout/stderr streams
    output_kwargs = subdict(final_kwargs, ["quiet", "discard_output"])
    stdout = _process_output(sys.stdout, result["stdout"], **output_kwargs)
    stderr = _process_output(sys.stderr, result["stderr"], **output_kwargs)

    # command must have finished before we have access to return code
    return_code = result["return_code"]()
    result.update(
        {
            "stdout": stdout,
            "stderr": stderr,
            "return_code": return_code,
            "failed": return_code > 0,
            "succeeded": return_code == 0,
        }
    )

    if result["succeeded"]:
        return result

    err_msg = "remote() encountered an error (return code %s) while executing %r" % (
        result["return_code"],
        command,
    )

    # if `warn_only` is True this function may still return a result
    return abort(result, err_msg, **final_kwargs)


# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L1100
def remote_sudo(command, **kwargs):
    "exactly the same as `remote`, but the given command is run as the root user"
    # user=None  # ignore
    # group=None # ignore
    kwargs["use_sudo"] = True
    return remote(command, **kwargs)


# https://github.com/mathiasertl/fabric/blob/master/fabric/contrib/files.py#L15
def remote_file_exists(path, **kwargs):
    "returns True if given path exists on remote system"
    # note: Fabric is doing something weird and clever here:
    # - https://github.com/mathiasertl/fabric/blob/master/fabric/contrib/files.py#L474-L485
    # but their examples don't work:

    # $ /bin/sh
    # sh-5.0$ foo="$(echo /usr/\*/share)"
    # sh-5.0$ echo $foo
    # /usr/*/share
    # sh-5.0$ exit
    # $ echo $SHELL
    # $ /bin/bash
    # $ foo="$(echo /usr/\*/share)"
    # $ echo $foo
    # /usr/*/share

    # TODO: revisit
    # update 2020/01: it does work, I just had no "/usr/[anything]/share" directories.
    # this works for me:
    #   foo=$(echo /\*/share/)
    #   echo $foo
    #   /usr/share/

    base_kwargs = {
        "use_sudo": False,
    }
    global_kwargs, user_kwargs, final_kwargs = handle(base_kwargs, kwargs)

    # do not raise an exception if remote file doesn't exist
    final_kwargs["warn_only"] = True

    remote_fn = remote_sudo if final_kwargs["use_sudo"] else remote
    command = "test -e %s" % path
    return remote_fn(command, **final_kwargs)["return_code"] == 0


# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L1157
def local(command, **kwargs):
    "preprocesses given `command` and options before executing it locally using Python's `subprocess.Popen`"
    base_kwargs = {
        "use_sudo": False,
        "use_shell": True,
        "combine_stderr": True,
        "capture": False,
        "timeout": None,
        "quiet": False,
        "display_running": True,
        "warn_only": False,  # https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L301-L305
        "abort_exception": RuntimeError,
    }
    global_kwargs, user_kwargs, final_kwargs = handle(base_kwargs, kwargs)

    if final_kwargs["capture"]:
        if final_kwargs["combine_stderr"]:
            out_stream = subprocess.PIPE
            err_stream = subprocess.STDOUT
        else:
            out_stream = subprocess.PIPE
            err_stream = subprocess.PIPE
    else:
        if final_kwargs["quiet"]:
            # we're not capturing and we've been told to be quiet
            # send everything to /dev/null
            out_stream = subprocess.DEVNULL
            err_stream = subprocess.DEVNULL
        else:
            out_stream = None
            err_stream = None

    if not final_kwargs["use_shell"] and not isinstance(command, list):
        raise ValueError("when shell=False, given command *must* be a list")

    if final_kwargs["use_shell"]:
        command = shell_wrap_command(command)

    if final_kwargs["use_sudo"]:
        if final_kwargs["use_shell"]:
            command = sudo_wrap_command(command)
        else:
            # lsh@2020-04: is this a good enough sudo command?
            # nothing uses local+noshell+sudo (at time of writing)
            command = ["sudo", "--non-interactive"] + command

    proc = subprocess.Popen(
        command, shell=final_kwargs["use_shell"], stdout=out_stream, stderr=err_stream
    )
    _print_running(command, sys.stdout, **final_kwargs)
    if final_kwargs["timeout"]:
        timer = Timer(final_kwargs["timeout"], proc.kill)
        try:
            timer.start()  # proximity matters
            stdout, stderr = proc.communicate()
        finally:
            timer.cancel()
    else:
        stdout, stderr = proc.communicate()

    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L1240-L1244
    result = {
        "return_code": proc.returncode,
        "failed": proc.returncode != 0,
        "succeeded": proc.returncode == 0,
        "command": command,
        "stdout": (stdout or b"").decode("utf-8").splitlines(),
        "stderr": (stderr or b"").decode("utf-8").splitlines(),
    }

    if result["succeeded"]:
        return result

    err_msg = "local() encountered an error (return code %s) while executing %r" % (
        result["return_code"],
        command,
    )

    # if `warn_only` is True this function may still return a result
    return abort(result, err_msg, **final_kwargs)


def single_command(cmd_list):
    "given a list of commands to run, returns a single command."
    # `remote` and `local` will do any escaping as necessary
    if cmd_list in [None, []]:
        return None
    return " && ".join(map(str, cmd_list))


def prompt(msg):
    """issues a prompt for input.
    raises a `PromptedException` if `abort_on_prompts` in `state.ENV` is `True` or executing within
    another process using `execute.parallel` where input can't be supplied.
    if `abort_exception` is set in `state.ENV`, then that exception is raised instead"""
    if state.ENV.get("abort_on_prompts", False):
        abort_ex = state.ENV.get("abort_exception", PromptedException)
        raise abort_ex("prompted with: %s" % (msg,))
    print(msg)
    try:
        return raw_input("> ")
    except NameError:
        return input("> ")


#
# uploads and downloads
#


def execute_rsync_command(cmd):
    """executes given rsync `cmd`, catching rsync errors and improving any errors raised.
    rsync commands can be generated with `_rsync_upload` and `_rsync_download` functions.
    """
    try:
        return local(cmd)
    except Exception as uncaught_exc:
        if hasattr(uncaught_exc, "result"):
            # this is a threadbare error and we may be able to improve it
            result = uncaught_exc.result
            # taken straight from the `man` page, authored "28 Jan 2018"
            error_map = {
                1: "Syntax or usage error",
                2: "Protocol incompatibility",
                3: "Errors selecting input/output files, dirs",
                4: "Requested  action  not supported: an attempt was made to manipulate 64-bit files on a platform that cannot support them; or an option was specified that is supported by the client and not by the server.",
                5: "Error starting client-server protocol",
                6: "Daemon unable to append to log-file",
                10: "Error in socket I/O",
                11: "Error in file I/O",
                12: "Error in rsync protocol data stream",
                13: "Errors with program diagnostics",
                14: "Error in IPC code",
                20: "Received SIGUSR1 or SIGINT",
                21: "Some error returned by waitpid()",
                22: "Error allocating core memory buffers",
                23: "Partial transfer due to error",
                24: "Partial transfer due to vanished source files",
                25: "The --max-delete limit stopped deletions",
                30: "Timeout in data send/receive",
                35: "Timeout waiting for daemon connection",
            }
            if result["return_code"] in error_map:
                raise NetworkError(
                    "rsync returned error %s: %s"
                    % (result["return_code"], error_map[result["return_code"]])
                )
        raise uncaught_exc


def _rsync_upload(local_path, remote_path, **kwargs):
    """generates an rsync command to copy `local_path` to `remote_path` using values in the current `state.ENV`.
    does *not* execute command. see `rsync_upload` and `execute_rsync_command`."""

    base_kwargs = subdict(
        _ssh_default_settings(), ["user", "host_string", "key_filename", "port"]
    )
    global_kwargs, user_kwargs, final_kwargs = handle(base_kwargs, kwargs)
    host_string = final_kwargs["host_string"]
    ip = 4
    if ":" in host_string:
        ip = 6

    if ip == 4:
        cmd = [
            "rsync",
            # '-i' is 'identity file'
            # note: without 'StrictHostKeyChecking' we'll be given a prompt during testing. is this solvable?
            "--rsh='ssh -i %s -p %s -o StrictHostKeyChecking=no'"
            % (final_kwargs["key_filename"], final_kwargs["port"]),
            local_path,
            "%s@%s:%s" % (final_kwargs["user"], host_string, remote_path),
        ]
    else:
        cmd = [
            "rsync",
            "--ipv6",
            "--rsh='ssh -6 -i %s -p %s -o StrictHostKeyChecking=no'"
            % (final_kwargs["key_filename"], final_kwargs["port"]),
            local_path,
            "%s@[%s]:%s" % (final_kwargs["user"], host_string, remote_path),
        ]

    return " ".join(cmd)


def rsync_upload(local_path, remote_path, **kwargs):
    "copies `local_path` to `remote_path` using values in the current `state.ENV`."
    remote_dir = os.path.dirname(remote_path)
    if not remote_file_exists(remote_dir):
        remote("mkdir -p %r" % remote_dir)
    return execute_rsync_command(_rsync_upload(local_path, remote_path, **kwargs))


def _rsync_download(remote_path, local_path, **kwargs):
    """generates an rsync command to copy `remote_path` to `local_path` using values in the current `state.ENV`.
    does *not* execute command. see `rsync_download` and `execute_rsync_command`."""
    base_kwargs = subdict(
        _ssh_default_settings(), ["user", "host_string", "key_filename", "port"]
    )
    global_kwargs, user_kwargs, final_kwargs = handle(base_kwargs, kwargs)
    host_string = final_kwargs["host_string"]
    ip = 4
    if ":" in host_string:
        ip = 6

    if ip == 4:
        cmd = [
            "rsync",
            # '-i' is 'identity file'
            # without 'StrictHostKeyChecking' we'll be given a prompt during testing.
            "--rsh='ssh -i %s -p %s -o StrictHostKeyChecking=no'"
            % (final_kwargs["key_filename"], final_kwargs["port"]),
            "%s@%s:%s" % (final_kwargs["user"], host_string, remote_path),
            local_path,
        ]
    else:
        cmd = [
            "rsync",
            "--ipv6",
            "--rsh='ssh -6 -i %s -p %s -o StrictHostKeyChecking=no'"
            % (final_kwargs["key_filename"], final_kwargs["port"]),
            "%s@[%s]:%s" % (final_kwargs["user"], host_string, remote_path),
            local_path,
        ]

    return " ".join(cmd)


def rsync_download(remote_path, local_path, **kwargs):
    "copies `remote_path` to `local_path` using values in the current `state.ENV`."
    abs_local_path = os.path.abspath(os.path.expanduser(local_path))
    abs_local_dir = os.path.dirname(abs_local_path)
    if not os.path.exists(abs_local_dir):
        # replicates behaviour of downloading via scp and sftp (via parallel-ssh)
        local("mkdir -p %r" % (abs_local_dir,))
    return execute_rsync_command(_rsync_download(remote_path, local_path, **kwargs))


def _transfer_fn(client, direction, **kwargs):
    """returns the `client` object's appropriate transfer *method* given a `direction`.
    `direction` is either 'upload' or 'download'.
    Also accepts the `transfer_protocol` keyword parameter that is either 'rsync' (default), 'scp' or 'sftp'.
    """
    base_kwargs = {
        "overwrite": True,
        # sftp is *exceptionally* slow.
        # Paramiko's implementation is faster than native SFTP but slower than SCP:
        # - https://github.com/ParallelSSH/parallel-ssh/issues/177
        # however, SCP is buggy and may randomly hang or complete without uploading anything.
        # take slow and reliable over fast and buggy.
        "transfer_protocol": "rsync",  # "sftp",  # "scp"
    }
    global_kwargs, user_kwargs, final_kwargs = handle(base_kwargs, kwargs)

    def upload_fn(fn):
        @wraps(fn)
        def wrapper(local_file, remote_file):
            if remote_file_exists(remote_file) and not final_kwargs["overwrite"]:
                raise NetworkError(
                    "Remote file exists and 'overwrite' is set to 'False'. Refusing to write: %s"
                    % (remote_file,)
                )

            if final_kwargs["transfer_protocol"] == "rsync":
                fn(local_file, remote_file)
            else:
                # https://github.com/ParallelSSH/parallel-ssh/blob/8b7bb4bcb94d913c3b7da77db592f84486c53b90/pssh/clients/native/parallel.py#L524
                g = fn(local_file, remote_file)
                if g:
                    gevent.joinall(g, raise_error=True)

            # lsh@2020-04, local testing didn't reveal anything but small files uploaded via SCP SCP during CI
            # were either missing or had empty bodies. SFTP seemed to be fine.
            # This sanity check seems to fix the issue (lending more credence to my theory it's an unflushed buffer somewhere),
            # when waiting 3 seconds between upload of file and check of file was still failing.
            ensure(
                remote_file_exists(remote_file, **kwargs),
                "failed to upload file, remote file does not exist: %s"
                % (remote_file,),
            )

        return wrapper

    def download_fn(fn):
        @wraps(fn)
        def wrapper(remote_file, local_file):

            if not final_kwargs["overwrite"] and os.path.exists(local_file):
                raise NetworkError(
                    "Local file exists and 'overwrite' is set to 'False'. Refusing to write: %s"
                    % (local_file,)
                )
            if final_kwargs["transfer_protocol"] == "rsync":
                fn(remote_file, local_file)
            else:
                # https://github.com/ParallelSSH/parallel-ssh/blob/d812ff32d828009ddb94f458fe43920c22df4c0e/pssh/clients/native/single.py#L558
                g = fn(remote_file, local_file)
                if g:
                    gevent.joinall(g, raise_error=True)

        return wrapper

    upload_backends = {
        "sftp": partial(client.copy_file, recurse=True),
        "scp": partial(client.scp_send, recurse=True),
        "rsync": rsync_upload,
    }

    download_backends = {
        "sftp": client.copy_remote_file,
        "scp": client.scp_recv,
        "rsync": rsync_download,
    }

    direction_map = {"upload": upload_backends, "download": download_backends}
    ensure(
        direction in direction_map,
        "you can 'upload' or 'download' but not %r" % (direction,),
    )

    backend_map = direction_map[direction]
    transfer_protocol = final_kwargs["transfer_protocol"]
    ensure(
        transfer_protocol in backend_map,
        "unhandled transfer protocol %r; supported protocols: %s"
        % (transfer_protocol, ", ".join(backend_map.keys())),
    )

    transfer_fn = direction_map[direction][transfer_protocol]

    direction_wrapper_map = {"upload": upload_fn, "download": download_fn}
    wrapper_fn = direction_wrapper_map[direction]

    return wrapper_fn(transfer_fn)


# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L419
# use_sudo hack: https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L453-L458
def _download_as_root_hack(remote_path, local_path, **kwargs):
    """as root, creates a temporary copy of the file that can be downloaded by a
    regular user and then removes the temporary file.
    warning: don't try to download anything huge `with_sudo` as the file is duplicated.
    warning: the privileged file will be available in /tmp until the download is complete
    """

    if not remote_file_exists(remote_path, use_sudo=True, **kwargs):
        raise EnvironmentError("remote file does not exist: %s" % (remote_path,))
    client = _ssh_client(**kwargs)

    cmd = single_command(
        [
            # create a temporary file with the suffix '-threadbare'
            'tempfile=$(mktemp --suffix "-threadbare")',
            # copy the target file to this temporary file
            'cp "%s" "$tempfile"' % remote_path,
            # ensure it's readable by the user doing the downloading
            'chmod +r "$tempfile"',
            # emit the name of the temporary file so we can find it to download it
            'echo "$tempfile"',
        ]
    )
    result = remote_sudo(cmd, **kwargs)
    remote_tempfile = result["stdout"][-1]
    remote_path = remote_tempfile

    transfer_fn = _transfer_fn(client, "download", **kwargs)

    try:
        transfer_fn(remote_tempfile, local_path)
        return local_path

    except (pssh.exceptions.SFTPError, pssh.exceptions.SCPError) as exc:
        # permissions or network issues may cause these
        raise WrappedNetworkError(exc)

    finally:
        remote_sudo('rm -f "%s"' % remote_tempfile, **kwargs)


# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L419
# use_sudo hack: https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L453-L458
def download(remote_path, local_path, use_sudo=False, **kwargs):
    """downloads file at `remote_path` to `local_path`, overwriting the local path if it exists.
    avoid `use_sudo` if at all possible"""

    with state.settings(quiet=True):
        if remote_path.endswith("/"):
            raise ValueError("directory downloads are not supported")

        # do not raise an exception if remote path is a directory
        result = remote(
            'test -d "%s"' % remote_path, use_sudo=use_sudo, warn_only=True, quiet=True
        )
        remote_path_is_dir = result["succeeded"]
        if remote_path_is_dir:
            raise ValueError("directory downloads are not supported")

        temp_file, data_buffer = None, None
        if hasattr(local_path, "read"):
            # given a file-like object to download file into.
            # 1. write the remote file to local temporary file
            # 2. read temporary file into the given buffer
            # 3. delete the temporary file

            data_buffer = local_path
            temp_file, local_path = tempfile.mkstemp(suffix="-threadbare")

        if not os.path.isabs(local_path):
            local_path = os.path.abspath(local_path)

        if os.path.isdir(local_path):
            local_path = os.path.join(local_path, os.path.basename(remote_path))

        if use_sudo:
            local_path = _download_as_root_hack(remote_path, local_path, **kwargs)

        else:
            if not remote_file_exists(remote_path, **kwargs):
                raise EnvironmentError(
                    "remote file does not exist: %s" % (remote_path,)
                )
            client = _ssh_client(**kwargs)
            transfer_fn = _transfer_fn(client, "download", **kwargs)

            try:
                transfer_fn(remote_path, local_path)
            except (pssh.exceptions.SFTPError, pssh.exceptions.SCPError) as exc:
                # permissions or network issues may cause these
                raise WrappedNetworkError(exc)

        if temp_file:
            flags = "r" if isinstance(data_buffer, io.StringIO) else "rb"
            with open(local_path, flags) as fh:
                data = fh.read()
            data_buffer.write(data)
            # deletes the *temporary file*. `temp_file` is a file descriptor
            os.unlink(local_path)
            return data_buffer

        return local_path


def _upload_as_root_hack(local_path, remote_path, **kwargs):
    """uploads file at `local_path` to a remote temporary file then moves the file to `remote_path` as root.
    does not alter any permissions or attributes on the file"""

    client = _ssh_client(**kwargs)

    cmd = single_command(
        [
            # create a temporary file with the suffix '-threadbare'
            'tempfile=$(mktemp --suffix "-threadbare")',
            'echo "$tempfile"',
        ]
    )
    result = remote(cmd, **kwargs)
    remote_temp_path = result["stdout"][-1]
    ensure(
        remote_file_exists(remote_temp_path, **kwargs),
        "remote temporary file %r (%s) does not exist"
        % (remote_temp_path, remote_path),
    )

    transfer_fn = _transfer_fn(client, "upload", **kwargs)

    try:
        transfer_fn(local_path, remote_temp_path)
        move_file_into_place = 'mv "%s" "%s"' % (remote_temp_path, remote_path)
        remote_sudo(move_file_into_place, **kwargs)
        ensure(
            remote_file_exists(remote_path, use_sudo=True, **kwargs),
            "remote path does not exist: %s" % (remote_path),
        )
    except (pssh.exceptions.SFTPError, pssh.exceptions.SCPError) as exc:
        # permissions or network issues may cause these
        raise WrappedNetworkError(exc)


def _write_bytes_to_temporary_file(local_path):
    """if `local_path` is a file-like object, write the contents to an *actual* file and
    return a pair of new local filename and a function that removes the temporary file when called.
    """
    if hasattr(local_path, "read"):
        # `local_path` is a file-like object
        local_bytes = local_path
        local_bytes.seek(0)  # reset internal pointer
        temp_file, local_path = tempfile.mkstemp(suffix="-threadbare")
        with os.fdopen(temp_file, "wb") as fh:
            data = local_bytes.getvalue()
            # data may be a string or it may be bytes.
            # if it's a string we assume it's a UTF-8 string.
            if isinstance(data, str):
                data = bytes(data, "utf-8")
            fh.write(data)
        cleanup = lambda: os.unlink(local_path)
        return local_path, cleanup
    return local_path, None


def upload(local_path, remote_path, use_sudo=False, **kwargs):
    "uploads file at `local_path` to the given `remote_path`, overwriting anything that may be at that path"
    # todo: this setting is dubious, don't count on it hanging around
    with state.settings(quiet=True):

        # bytes handling
        local_path, cleanup_fn = _write_bytes_to_temporary_file(local_path)
        if cleanup_fn:
            state.add_cleanup(cleanup_fn)

        if os.path.isdir(local_path):
            raise ValueError("folders cannot be uploaded")

        if use_sudo:
            return _upload_as_root_hack(local_path, remote_path, **kwargs)

        if not os.path.exists(local_path):
            raise EnvironmentError("local file does not exist: %s" % (local_path,))

        client = _ssh_client(**kwargs)

        try:
            transfer_fn = _transfer_fn(client, "upload", **kwargs)
            transfer_fn(local_path, remote_path)
        except (pssh.exceptions.SFTPError, pssh.exceptions.SCPError) as exc:
            # permissions or network issues may cause these
            raise WrappedNetworkError(exc)
