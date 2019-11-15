import os
import socket
import ssh2.session
import threadbare
from threadbare import merge

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

# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L726-L856
def _execute(command, user, private_key_file, host, port, use_pty):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    
    session = ssh2.session.Session()
    session.handshake(sock)
    
    session.userauth_publickey_fromfile(user, private_key_file)
    channel = session.open_session()

    # https://ssh2-python.readthedocs.io/en/latest/channel.html#ssh2.channel.Channel.pty
    use_pty and channel.pty()

    # https://ssh2-python.readthedocs.io/en/latest/channel.html#ssh2.channel.Channel.execute
    channel.execute(command)

    # https://github.com/ParallelSSH/ssh2-python/blob/master/examples/example_echo.py#L39-L41
    channel.wait_eof()
    channel.close()
    channel.wait_closed()

    # reading output
    size, data = channel.read()
    buff = b''
    while(size > 0):
        # buffers output in ram
        buff += data
        size, data = channel.read()

    session.disconnect()

    return {
        'return_code': channel.get_exit_status(),
        'command': command,
        'bytes': buff,

        # todo: the buffered output and this need to be re-thought.
        # probably when I take a look at how stdout/stderr/stdin pipes are handled
        'lines': lambda: buff.decode('utf-8').splitlines(),
    }

# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L898-L901
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L975
def remote(command, use_shell=True, use_sudo=False, **kwargs): #host=None, port=None, private_key_file=None, use_sudo=False, use_shell=True, **kwargs):
    #shell=True # done
    #pty=True   # done
    #combine_stderr=None
    #quiet=False,
    #warn_only=False
    #stdout=None # todo
    #stderr=None # todo
    #timeout=None # todo
    #shell_escape=None # ignored. shell commands are always escaped
    #capture_buffer_size=None # correlates to `ssh2.channel.read` and the `size` parameter. Ignored.

    # wrap the command up
    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L920-L925
    if use_shell:
        command = shell_wrap_command(command)
    if use_sudo:
        command = sudo_wrap_command(command)

    # values stored in global state, if any (global state is *empty* by default)
    global_kwargs = threadbare.get_settings(key_list=['user', 'host', 'port', 'private_key_file'])

    # values that would otherwise be function parameter defaults or calculated somewhere
    # should these live here?
    base_kwargs = {
        'private_key_file': os.path.expanduser("~/.ssh/id_rsa"),
        'port': 22
    }

    # values the user has passed in - *explicit* overrides
    user_kwargs = threadbare.get_settings(kwargs, key_list=['user', 'host', 'port', 'private_key_file'])

    # values `remote` specifically passes to `_execute`, overriding all others
    cmd_kwargs = {
        'command': command,

        # the two are not synonymous, but we'll pretend they are
        # we get ansi control characters (colours!) when salt detects a pseudo terminal
        'use_pty': use_shell,
    }

    # final dictionary of keyword parameters that `_execute` receives
    final_kwargs = merge(global_kwargs, base_kwargs, user_kwargs, cmd_kwargs)

    return _execute(**final_kwargs)

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
    with threadbare.settings(user='elife', host='34.201.187.7'):
        #result = remote_sudo('salt-call pillar.items')
        #result = remote_sudo(r'echo -e "\e[31mRed Text\e[0m"', use_shell=False)
        result = remote('echo "stdout"; >&2 echo "stderr"')
        result = remote('errcho() { echo "$@" >&2; }; errcho hello')
        print('---')
        for line in result['lines']():
            print(line)
        print('---')
        del result['bytes'] # noisy
        print(result)
    
if __name__ == '__main__':
    main()
