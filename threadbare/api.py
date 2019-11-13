import os
import socket
from ssh2.session import Session

# direct copy from fabric:
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L33-L46
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
        string = string.replace(char, '\%s' % char)
    return string

def shell_wrap_command(command):
    # https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L253-L256
    # '-l' is 'login' shell
    # '-c' is 'run command'
    space = " "
    shell_prefix = "/bin/bash -l -c"

    escaped_command = _shell_escape(command)
    escaped_wrapped_command = '"%s"' % escaped_command

    final_command = shell_prefix + space + escaped_wrapped_command

    return final_command

def sudo_wrap_command(command):
    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L605-L623
    # https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L374-L376
    # note: differs from Fabric. they support interactive input of password, users and groups
    # we use it exclusively to run commands as root
    sudo_prefix = "sudo --non-interactive"
    space = " "
    return sudo_prefix + space + command

#

# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L726-L856
def _execute(command, use_pty=False, **kwargs):
    username = 'elife'
    host, port = '34.201.187.7', 22
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    
    session = Session()
    session.handshake(sock)
    
    #print(session.userauth_list(username)) # list of authentication methods available

    private_key_file = os.path.expanduser("~/.ssh/id_rsa")
    session.userauth_publickey_fromfile(username, private_key_file)
    
    # executing commands
    channel = session.open_session()

    if use_pty:
        # https://ssh2-python.readthedocs.io/en/latest/channel.html#ssh2.channel.Channel.pty
        channel.pty()
    
    channel.execute(command)

    # reading output
    size, data = channel.read()
    buff = b''
    while(size > 0):
        # this will print the data out in chunks of $size until all is read
        #print(data.decode('utf-8'))

        # this will buffer the output in memory
        buff += data
        size, data = channel.read()

    return {
        'return_code': channel.get_exit_status(),
        'command': command,
        'bytes': buff,
        'lines': lambda: buff.decode('utf-8').splitlines()
    }

# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L898-L901
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L975
def remote(command, use_sudo=False, use_shell=True, **kwargs):
    #shell=True # done
    #pty=True   # done
    #combine_stderr=None
    #quiet=False,
    #warn_only=False
    #stdout=None # todo
    #stderr=None # todo
    #timeout=None # todo
    #shell_escape=None
    #capture_buffer_size=None
    
    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L920-L925
    
    if use_shell:
        command = shell_wrap_command(command)
    if use_sudo:
        command = sudo_wrap_command(command)

    # the two are not synonymous, but we'll pretend they are
    # we get ansi control characters (colours!) when a pseudo terminal is requested
    use_pty = use_shell 
        
    return _execute(command, use_pty)

# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L1100
def remote_sudo(command, **kwargs):
    # user=None
    # group=None
    return remote(command, use_sudo=True, **kwargs)

#
#
#

def main():
    #result = remote_sudo('salt-call pillar.items')
    result = remote('echo hi')
    result = remote('echo -e "\e[31mRed Text\e[0m"', use_shell=False)
    print('---')
    for line in result['lines']():
        print(line)
    print('---')
    #del result['bytes']
    print(result)
    
if __name__ == '__main__':
    main()
