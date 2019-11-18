from pssh.clients.native import SSHClient
import os, sys
import threadbare
from threadbare.common import merge, subdict

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

def _execute(command, user, private_key_file, host, port, use_pty):
    # https://parallel-ssh.readthedocs.io/en/latest/native_single.html#pssh.clients.native.single.SSHClient
    password = None
    client = SSHClient(host, user, password, port, pkey=private_key_file)
    
    # https://github.com/ParallelSSH/parallel-ssh/blob/1.9.1/pssh/clients/native/single.py#L408
    sudo = False # handled ourselves
    shell = False # handled ourselves
    timeout = None # todo
    encoding = 'utf-8' # default everywhere
    channel, host, stdout, stderr, stdin = client.run_command(command, sudo, user, use_pty, shell, encoding, timeout)

    def get_exitcode():
        client.wait_finished(channel) # timeout here
        return channel.get_exit_status()

    return {
        'return_code': get_exitcode,
        'command': command,
        'stdout': stdout,
        'stderr': stderr,
    }

def streaming_print(output_pipe, quiet, discard_output, line):
    """writes the given `line` (string) to the given `output_pipe` (file-like object) if `quiet` is True. 
    returns the given line if `discard_output` is False

    this allows some control over 
    then fiddle about with the data after the fact.
    if you're expecting very very large responses, `discard_output` should be set to `True`."""
    if not quiet:
        output_pipe.write(line + "\n")
    if not discard_output:
        return line

def _process_output(output_pipe, result_list, quiet, discard_output):
    cmd_kwargs = subdict(locals(), ['quiet', 'discard_output'])
    global_kwargs = subdict(threadbare.ENV, ['quiet', 'discard_output'])
    kwargs = merge(cmd_kwargs, global_kwargs)

    # always process the results as soon as we have them
    # use `quiet` to hide the printing of output to stdout/stderr
    # use `discard_output` to discard the results as soon as they are read
    # stderr may be empty if `combine_stderr` in `remote` was `True`
    new_results = [streaming_print(output_pipe, line=line, **kwargs) for line in result_list]
    output_pipe.flush()
    if not kwargs['discard_output']:
        return new_results

# https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L338
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L898-L901
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L975
def remote(command, use_shell=True, use_sudo=False, combine_stderr=True, quiet=False, discard_output=False, **kwargs):
    #shell=True # done
    #pty=True   # mutually exclusive with combine_stderr. not sure what Fabric/Paramiko is doing here
    #combine_stderr=None # mutually exclusive with use_pty. 'True' in global env.
    #quiet=False,
    #warn_only=False
    #stdout=None # ignore
    #stderr=None # ignore
    #timeout=None # todo
    #shell_escape=None # ignored. shell commands are always escaped
    #capture_buffer_size=None # correlates to `ssh2.channel.read` and the `size` parameter. Ignored.

    # wrap the command up
    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L920-L925
    if use_shell:
        command = shell_wrap_command(command)
    if use_sudo:
        command = sudo_wrap_command(command)

    # if use_pty is True, stdout and stderr are combined and stderr will yield nothing.
    # bug or expected behaviour in parallel-ssh?
    use_pty = combine_stderr

    # values stored in global state, if any (global state is *empty* by default)
    global_kwargs = subdict(threadbare.ENV, ['user', 'host', 'port', 'private_key_file'])

    # values that would otherwise be function parameter defaults or calculated somewhere
    # should these live here?
    base_kwargs = {
        'private_key_file': os.path.expanduser("~/.ssh/id_rsa"),
        'port': 22
    }

    # values the user has passed in - *explicit* overrides
    user_kwargs = subdict(kwargs, ['user', 'host', 'port', 'private_key_file'])

    # values `remote` specifically passes to `_execute`, overriding all others
    cmd_kwargs = {
        'command': command,
        'use_pty': use_pty
    }

    # final dictionary of keyword parameters that `_execute` receives
    final_kwargs = merge(base_kwargs, user_kwargs, global_kwargs, cmd_kwargs)

    # print('args to execute:',final_kwargs)
    
    result = _execute(**final_kwargs)

    result.update({
        'stdout': _process_output(sys.stdout, result['stdout'], quiet, discard_output),
        'stderr': _process_output(sys.stderr, result['stderr'], quiet, discard_output),

        # command must have finished before we have access to return code
        'return_code': result['return_code'](), 
    })

    return result

# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L1100
def remote_sudo(command, **kwargs):
    # user=None  # ignore
    # group=None # ignore
    kwargs['use_sudo'] = True
    return remote(command, **kwargs)

#
#
#

def main():
    # it's embarassing how nice it is to play with global state...
    with threadbare.settings(user='elife', host='34.201.187.7', quiet=False, discard_output=False) as env:
        #result = remote(r'echo -e "\e[31mRed Text\e[0m"', use_shell=False)
        #result = remote('echo "standard out"; echo "sleeping"; sleep 2; >&2 echo "standard error"; exit 2', combine_stderr=False)
        #result = remote_sudo('salt-call state.highstate')
        # read from stdin
        result = remote('echo "> "; cat -')

        if env.get('quiet', False) and not env.get('discard_output', False):
            print('---')
            for line in result['stdout']:
                print('stdout:',line)

            for line in result['stderr']:
                print('stderr:',line)

        print('---')
        
        print('results:',result)
    
if __name__ == '__main__':
    main()
