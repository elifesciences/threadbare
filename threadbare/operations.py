import subprocess
import getpass
from pssh.clients.native import SSHClient
from pssh import exceptions as pssh_exceptions
import os, sys
from threadbare import state
from threadbare.common import merge, subdict

class NetworkError(BaseException):
    """generic 'died while doing something ssh-related' catch-all exception class.
    calling str() on this exception will return the results on calling str() on the 
    wrapped exception."""
    def __init__(self, wrapped_exception_inst):
        self.wrapped = wrapped_exception_inst

    def __str__(self):
        # we have the opportunity here to tweak the error messages to make them
        # similar with their equivalents in Fabric.
        # original error messages are still available via `str(exinst.wrapped)`
        space = " "
        custom_error_prefixes = {
            # builder: https://github.com/elifesciences/builder/blob/master/src/buildercore/core.py#L345-L347
            # pssh: https://github.com/ParallelSSH/parallel-ssh/blob/8b7bb4bcb94d913c3b7da77db592f84486c53b90/pssh/clients/native/parallel.py#L272-L274
            pssh_exceptions.Timeout: "Timed out trying to connect." + space,

            # builder: https://github.com/elifesciences/builder/blob/master/src/buildercore/core.py#L348-L350
            # fabric: https://github.com/mathiasertl/fabric/blob/master/fabric/network.py#L601-L605
            # pssh: https://github.com/ParallelSSH/parallel-ssh/blob/2e9668cf4b58b38316b1d515810d7e6c595c76f3/pssh/exceptions.py
            pssh_exceptions.SSHException: "Low level socket error connecting to host." + space,
            pssh_exceptions.SessionError: "Low level socket error connecting to host." + space,
            pssh_exceptions.ConnectionErrorException: "Low level socket error connecting to host." + space,
        }
        new_error = custom_error_prefixes.get(type(self.wrapped)) or ""
        original_error = str(self.wrapped)
        return new_error + original_error

# utils

# direct copy from Fabric:
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L33-L46
# TODO: adjust licence accordingly
def _shell_escape(string):
    """
    Escape double quotes, backticks and dollar signs in given ``string``.
    For example::
        >>> _shell_escape('abc$')
        'abc\\\\$'
        >>> _shell_escape('"')
        '\\\\"'
    """
    for char in ('"', '$', '`'):
        string = string.replace(char, r'\%s' % char)
    return string

# https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L253-L256
def shell_wrap_command(command):
    """wraps the given command in a shell invocation.
    default shell is /bin/bash (like Fabric)
    no support for configurable shell at present"""

    # '-l' is 'login' shell
    # '-c' is 'run command'
    shell_prefix = "/bin/bash -l -c"

    escaped_command = _shell_escape(command)
    escaped_wrapped_command = '"%s"' % escaped_command

    space = " "
    final_command = shell_prefix + space + escaped_wrapped_command

    return final_command

def sudo_wrap_command(command):
    """adds a 'sudo' prefix to command to run as root. 
    no support for sudo'ing to configurable users/groups"""
    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L605-L623
    # https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L374-L376
    # note: differs from Fabric. they support interactive input of password, users and groups
    # we use it exclusively to run commands as root
    sudo_prefix = "sudo --non-interactive"
    space = " "
    return sudo_prefix + space + command

# api

# todo: 'api.py' and '__init__.py' are poorly named and this function + a `local` function
# should probably be wrapped `__init__/execute`
def _execute(command, user, key_filename, host_string, port, use_pty):
    """creates an SSHClient object and executes given `command` with the given parameters.
    it does not consult global state and all parameters must be explicitly passed in.
    keep this function as simple as possible."""

    # https://parallel-ssh.readthedocs.io/en/latest/native_single.html#pssh.clients.native.single.SSHClient
    password = None # we *never* use passwords, not even for bootstrapping. always private keys.
    client = SSHClient(host_string, user, password, port, pkey=key_filename)
    
    # https://github.com/ParallelSSH/parallel-ssh/blob/1.9.1/pssh/clients/native/single.py#L408
    sudo = False # handled ourselves
    shell = False # handled ourselves
    timeout = None # todo
    encoding = 'utf-8' # default everywhere

    try:
        channel, host_string, stdout, stderr, stdin = client.run_command(command, sudo, user, use_pty, shell, encoding, timeout)

        def get_exitcode():
            """we can't know the exit code until command has finished running but we *can* access
            the output streams. attempting to realise the exitcode will cause the thread of execution 
            to block until the channel is finished"""
            client.wait_finished(channel) # `timeout` here
            return channel.get_exit_status()

        return {
            'return_code': get_exitcode,
            'command': command,
            'stdout': stdout,
            'stderr': stderr,
        }
    except BaseException as ex:
        # *most likely* a network error:
        # https://github.com/ParallelSSH/parallel-ssh/blob/master/pssh/exceptions.py
        raise NetworkError(ex)

def _print_line(output_pipe, quiet, discard_output, line):
    """writes the given `line` (string) to the given `output_pipe` (file-like object)
    if `quiet` is False, `line` is not written.
    if `discard_output` is False, `line` is not returned.
    `discard_output` should be set to `True` when you're expecting very large responses."""
    if not quiet:
        output_pipe.write(line + "\n")
    if not discard_output:
        return line

def _process_output(output_pipe, result_list, quiet, discard_output):
    "calls `_print_line` on each result in `result_list`."
    kwargs = subdict(locals(), ['quiet', 'discard_output'])

    # always process the results as soon as we have them
    # use `quiet` to hide the printing of output to stdout/stderr
    # use `discard_output` to discard the results as soon as they are read
    # stderr may be empty if `combine_stderr` in `remote` was `True`
    new_results = [_print_line(output_pipe, line=line, **kwargs) for line in result_list]
    output_pipe.flush()
    if not kwargs['discard_output']:
        return new_results

# https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L338
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L898-L901
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L975
def remote(command, **kwargs):
    "preprocesses given `command` and options before sending it to `_execute` to be executed on remote host"

    # Fabric function signature for `run`
    #shell=True # done
    #pty=True   # mutually exclusive with combine_stderr. not sure what Fabric/Paramiko is doing here
    #combine_stderr=None # mutually exclusive with use_pty. 'True' in global env.
    #quiet=False, # done
    #warn_only=False # ignore
    #stdout=None # done, stdout/stderr always available unless explicitly discarded. 'see discard_output'
    #stderr=None # done, stderr not available when combine_stderr is `True`
    #timeout=None # todo
    #shell_escape=None # ignored. shell commands are always escaped
    #capture_buffer_size=None # correlates to `ssh2.channel.read` and the `size` parameter. Ignored.

    # parameters we're interested in and their default values
    base_kwargs = {
        # current user. sensible default but probably not what you want
        'user': getpass.getuser(),
        'host_string': None,
        'key_filename': os.path.expanduser("~/.ssh/id_rsa"),
        'port': 22,
        'use_shell': True,
        'use_sudo': False,
        'combine_stderr': True,
        'quiet': False,
        'discard_output': False,
    }

    #print('global state', state.ENV)
    
    # values available in global state, if any - implicit overrides
    global_kwargs = subdict(state.ENV, base_kwargs.keys())
    
    # values user passed in - explicit overrides
    user_kwargs = subdict(kwargs, base_kwargs.keys())

    final_kwargs = merge(base_kwargs, global_kwargs, user_kwargs)

    # wrap the command up
    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L920-L925
    if final_kwargs['use_shell']:
        command = shell_wrap_command(command)
    if final_kwargs['use_sudo']:
        command = sudo_wrap_command(command)
        
    # if use_pty is True, stdout and stderr are combined and stderr will yield nothing.
    # bug or expected behaviour in parallel-ssh?
    use_pty = final_kwargs['combine_stderr']
    
    # values `remote` specifically passes to `_execute`
    execute_kwargs = {
        'command': command,
        'use_pty': use_pty
    }
    execute_kwargs = merge(final_kwargs, execute_kwargs)
    execute_kwargs = subdict(execute_kwargs, ['command', 'user', 'key_filename', 'host_string', 'port', 'use_pty'])
    # TODO: validate `_execute`s args. `host_string` can't be None for example

    #print('final kwargs',execute_kwargs)
    
    # run command
    result = _execute(**execute_kwargs)

    # handle stdout/stderr streams
    output_kwargs = subdict(final_kwargs, ['quiet', 'discard_output'])
    result.update({
        'stdout': _process_output(sys.stdout, result['stdout'], **output_kwargs),
        'stderr': _process_output(sys.stderr, result['stderr'], **output_kwargs),

        # command must have finished before we have access to return code
        'return_code': result['return_code'](), 
    })

    return result


# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L1100
def remote_sudo(command, **kwargs):
    "exactly the same as `remote`, but the given command is run as the root user"
    # user=None  # ignore
    # group=None # ignore
    kwargs['use_sudo'] = True
    return remote(command, **kwargs)


# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L1157
def local(command, **kwargs):
    base_kwargs = {
        'use_shell': True,
        'combine_stderr': True,
        'capture': False,
    }
    global_kwargs = subdict(state.ENV, base_kwargs.keys())
    user_kwargs = subdict(kwargs, base_kwargs.keys())
    final_kwargs = merge(base_kwargs, global_kwargs, user_kwargs)

    if final_kwargs['capture']:
        if final_kwargs['combine_stderr']:
            out_stream = subprocess.PIPE
            err_stream = subprocess.STDOUT
        else:
            out_stream = subprocess.PIPE
            err_stream = subprocess.PIPE
    else:
        out_stream = None
        err_stream = None

    if not final_kwargs['use_shell'] and not isinstance(command, list):
        raise ValueError("when shell=False, given command *must* be a list")
        
    if final_kwargs['use_shell']:
        command = shell_wrap_command(command)

    p = subprocess.Popen(command, shell=final_kwargs['use_shell'], stdout=out_stream, stderr=err_stream)
    stdout, stderr = p.communicate()

    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L1240-L1244    
    return {
        'return_code': p.returncode,
        'failed': p.returncode > 0,
        'succeeded': p.returncode == 0,
        'command': command,
        'stdout': (stdout or b'').decode('utf-8').splitlines(),
        'stderr': (stderr or b'').decode('utf-8').splitlines(),
    }
