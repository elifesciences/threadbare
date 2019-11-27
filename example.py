import os
from threadbare import state
from threadbare.state import settings
from threadbare.operations import remote, remote_file_exists, remote_sudo, local, download, upload, single_command

def handle_result(result):
    env = state.ENV # or, `with settings() as env` works just as well
    if env.get('quiet', False) and not env.get('discard_output', False):
        print('---')
        for line in result['stdout']:
            print('out:',line)

        for line in result['stderr']:
            print('err:',line)

    print('---')
        
    print('results:',result)

def run_a_remote_command():
    with settings(quiet=False):
        print(remote(r'echo -e "\e[31mDanger Will Robinson!\e[0m"', use_shell=False))
        print(remote('echo "standard out"; >&2 echo "standard error"; exit 123', combine_stderr=False))
        print(remote('foo=bar; echo "bar? $foo!"', use_shell=False))

def run_a_local_command():
    print(local("echo hello, world!"))
    
def nest_some_settings():
    with settings(foo='bar'):
        with settings(bar='baz'):
            with settings(baz='bup'):
                print("After three nestings I have the cumulate state: %s" % state.ENV)

def run_many_remote_commands():
    with settings(quiet=False):
        command_list = [
            "echo all",
            "echo these commands",
            "echo share the same",
            "echo ssh session"
        ]
        for command in command_list:
            print(remote(command))

def run_a_remote_command_as_root():
    print(remote_sudo("cd /root && echo tapdance in $(pwd)"))

def upload_a_file(local_file_name):
    local_file_contents = "foo"
    with open(local_file_name, 'w') as fh:
        fh.write(local_file_contents)
    remote_file_name = '/tmp/threadbare-payload.tmp'
    upload(local_file_name, remote_file_name)
    assert remote_file_exists(remote_file_name)
    return remote_file_name

def modify_remote_file(remote_file_name):
    remote('printf "bar" >> %s' % remote_file_name)

def modify_local_file(local_file_name):
    local('printf "baz" >> %s' % local_file_name)

def download_a_file(remote_file_name):
    new_local_file_name = '/tmp/threadbare-payload.tmp2'
    download(remote_file_name, new_local_file_name)
    remote('rm %s' % remote_file_name)
    return new_local_file_name

def composite_actions():
    "write a local file, upload it to the remote server, modify it remotely, download it, modify it again, assert it's contents are as expected"

    print('uploading file ...')
    local_file_name = '/tmp/threadbare-payload.tmp'
    uploaded_file = upload_a_file(local_file_name)

    print('modifying remote file ...')
    modify_remote_file(uploaded_file)

    print('downloading file ...')
    new_local_file_name = download_a_file(uploaded_file)

    print('modifying local file ...')
    modify_local_file(new_local_file_name)
    
    with open(new_local_file_name, 'r') as fh:
        data = fh.read()

    print('testing local file ...')
    assert data == "foobarbaz"

    print('good!')

def download_file_owned_by_root():
    print('creating a root-only file on remote machine ...')
    remote_file_name = "/root/threadbare-test.temp"
    file_contents = "root users only!\n"
    remote_sudo(single_command([
        'printf "%s" > "%s"' % (file_contents, remote_file_name),
        'chmod 600 "%s"' % remote_file_name
    ]))

    print("ensuring local file doesn't exist ...")
    local_file_name = "/tmp/threadbare-test.temp"
    local('rm -f "%s"' % local_file_name)

    print('ensuring remote root-only file cannot be seen or downloaded by regular user %r' % state.ENV['user'])
    try:
        download(remote_file_name, local_file_name)
        assert False, "remote file shouldn't be detectable!"
    except EnvironmentError:
        # file undetectable by regular user!
        pass

    print('downloading remote root-only file as regular user %r' % state.ENV['user'])
    download(remote_file_name, local_file_name, use_sudo=True)
    print('testing')
    assert os.path.exists(local_file_name)
    print('ensuring contents match ...')
    assert open(local_file_name, 'r').read() == file_contents

    print('removing remote root-only file')
    remote_sudo('rm -f "%s"' % remote_file_name)
    
    print('done!')
    
def main():
    #nest_some_settings()
    #run_a_local_command()
    with settings(user='elife', host_string='34.201.187.7', quiet=False, discard_output=False):
        #run_a_remote_command()
        #run_a_remote_command_as_root()
        #run_many_remote_commands()
        #composite_actions()
        download_file_owned_by_root()
        
if __name__ == '__main__':
    main()
