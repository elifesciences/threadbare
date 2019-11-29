import os
from io import BytesIO
from threadbare import state
from threadbare.state import settings
from threadbare.operations import remote, remote_file_exists, remote_sudo, local, download, upload, single_command, lcd, rcd

def nest_some_settings():
    "demonstrates how settings accumulate"
    with settings(foo='bar'):
        with settings(bar='baz'):
            with settings(baz='bup'):
                print("after three nestings I have the cumulate state: %s" % state.ENV)

def run_a_local_command():
    "run a simple local command"
    print(local("echo hello, world!"))

def run_a_local_command_with_separate_streams():
    "run a simple local command but capture the output"
    print(local("echo hello, world!", capture=True))

def run_a_local_command_in_a_different_dir():
    "switch to a different local directory to run a command"
    with lcd("/tmp"):
        print(local("pwd", capture=True))

def run_a_remote_command():
    "run a simple remote command"
    print(remote(r'echo -e "\e[31mDanger Will Robinson!\e[0m"'))

def run_a_remote_command_in_a_different_dir():
    with rcd("/tmp"):
        print(remote("pwd"))

def run_a_remote_command_as_root():
    print(remote_sudo("cd /root && echo tapdance in $(pwd)"))
    
def run_a_remote_command_with_separate_streams():
    "run a simple remote command and capture stdout and stderr separately"
    print(remote('echo "standard out"; >&2 echo "standard error"; exit 123', combine_stderr=False))

def run_a_remote_command_with_shell_interpolation():
    "run a simple remote command including variables"
    print(remote('foo=bar; echo "bar? $foo!"'))
    print(remote('foo=bar; echo "bar? $foo!"', use_shell=False))

def run_many_remote_commands():
    "running many remote commands re-uses the established ssh session"
    command_list = [
        "echo all",
        "echo these commands",
        "echo share the same",
        "echo ssh session"
    ]
    for command in command_list:
        print(remote(command))

def run_many_remote_commands_singly():
    "running many remote commands re-uses the established ssh session"
    command_list = [
        "echo all",
        "echo these commands",
        "echo are executed",
        "echo together"
    ]
    print(remote(single_command(command_list)))

def run_many_remote_commands_serially():
    pass
    
def run_many_remote_commands_in_parallel():
    pass

def _upload_a_file(local_file_name):
    local_file_contents = "foo"
    with open(local_file_name, 'w') as fh:
        fh.write(local_file_contents)
    remote_file_name = '/tmp/threadbare-payload.tmp'
    upload(local_file_name, remote_file_name)
    assert remote_file_exists(remote_file_name)
    return remote_file_name

def _modify_remote_file(remote_file_name):
    remote('printf "bar" >> %s' % remote_file_name)

def _download_a_file(remote_file_name):
    new_local_file_name = '/tmp/threadbare-payload.tmp2'
    download(remote_file_name, new_local_file_name)
    remote('rm %s' % remote_file_name)
    return new_local_file_name
    
def _modify_local_file(local_file_name):
    local('printf "baz" >> %s' % local_file_name)

def upload_and_download_a_file():
    "write a local file, upload it to the remote server, modify it remotely, download it, modify it again, assert it's contents are as expected"

    print('uploading file ...')
    local_file_name = '/tmp/threadbare-payload.tmp'
    uploaded_file = _upload_a_file(local_file_name)

    print('modifying remote file ...')
    _modify_remote_file(uploaded_file)

    print('downloading file ...')
    new_local_file_name = _download_a_file(uploaded_file)

    print('modifying local file ...')
    _modify_local_file(new_local_file_name)

    print('testing local file ...')
    data = open(new_local_file_name, 'r').read()
    assert data == "foobarbaz"

    print('good!')

def download_file_owned_by_root():
    "a file owned by root can be downloaded by the regular user if 'use_sudo' is True"
    
    # create a root-only file on remote machine
    remote_file_name = "/root/threadbare-test.temp"
    file_contents = "root users only!\n"
    remote_sudo(single_command([
        'printf "%s" > "%s"' % (file_contents, remote_file_name),
        'chmod 600 "%s"' % remote_file_name
    ]))

    # ensure local file doesn't exist
    local_file_name = "/tmp/threadbare-test.temp"
    local('rm -f "%s"' % local_file_name)

    # ensure remote root-only file cannot be seen or downloaded by regular user
    try:
        download(remote_file_name, local_file_name)
        assert False, "remote file shouldn't be detectable!"
    except EnvironmentError:
        # file undetectable by regular user!
        pass

    # download remote root-only file as regular user
    download(remote_file_name, local_file_name, use_sudo=True)
    assert os.path.exists(local_file_name)
    assert open(local_file_name, 'r').read() == file_contents

    # cleanup. remove remote root-only file
    remote_sudo('rm -f "%s"' % remote_file_name)

def upload_file_to_root_dir():
    "uploads a file as a regular user to the /root directory with `use_sudo`"

    remote_file_name = "/root/threadbare-test.temp"
    remote_sudo('rm -f "%s"' % remote_file_name)
    assert not remote_file_exists(remote_file_name, use_sudo=True)

    local_file_name = "/tmp/threadbare-test.temp"
    local('echo foobarbaz > "%s"' % local_file_name)
    print('uploading file (this is *very* slow over SFTP)')
    upload(local_file_name, remote_file_name, use_sudo=True)
    print('done uploading')

    assert remote_file_exists(remote_file_name, use_sudo=True)

def upload_bytes_to_remote_file():
    unicode_buffer = BytesIO(b"foobarbaz")
    remote_file_name = '/tmp/threadbare-bytes-test.temp'
    upload(unicode_buffer, remote_file_name)
    print(remote('cat "%s"' % remote_file_name))
    return remote_file_name

def download_file_to_local_bytes(remote_file_name):
    assert remote_file_exists(remote_file_name)
    unicode_buffer = BytesIO()
    download(remote_file_name, unicode_buffer)
    print(unicode_buffer.getvalue())

def upload_and_download_a_file_using_bytes():
    with settings(quiet=True):
        remote_file_name = upload_bytes_to_remote_file()
        download_file_to_local_bytes(remote_file_name)

def main():
    '''
    nest_some_settings()
    run_a_local_command()
    run_a_local_command_with_separate_streams()
    run_a_local_command_in_a_different_dir()
    '''
    with settings(user='elife', host_string='34.201.187.7', quiet=False, discard_output=False):
        '''
        run_a_remote_command()
        run_a_remote_command_in_a_different_dir()
        run_a_remote_command_as_root()
        run_a_remote_command_with_separate_streams()
        run_a_remote_command_with_shell_interpolation()
        
        run_many_remote_commands()
        run_many_remote_commands_singly()
        run_many_remote_commands_serially()
        run_many_remote_commands_in_parallel()

        upload_and_download_a_file()
        upload_file_to_root_dir()
        download_file_owned_by_root()
        '''

        upload_and_download_a_file_using_bytes()

if __name__ == '__main__':
    main()
