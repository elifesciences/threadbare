from threadbare import operations, state
from threadbare.state import settings
from threadbare.operations import remote

def handle_result_1(result):
    env = state.ENV # global mutable state, beware.
    if env.get('quiet', False) and not env.get('discard_output', False):
        print('---')
        for line in result['stdout']:
            print('out:',line)

        for line in result['stderr']:
            print('err:',line)

    print('---')
        
    print('results:',result)

def handle_result_2(result):
    with settings() as env:
        if env.get('quiet', False) and not env.get('discard_output', False):
            print('---')
            for line in result['stdout']:
                print('out:',line)

            for line in result['stderr']:
                print('err:',line)

        print('---')
        
        print('results:',result)

def main():
    with settings(nest=0):
        print('hi')
        with settings(nest=1):
            print('hello')
            with settings(nest=2):
                print('hey')

    assert state.ENV.read_only
                
    return
    
    with settings(user='elife', host_string='34.201.187.7', quiet=False, discard_output=False):
        #result = remote(r'echo -e "\e[31mRed Text\e[0m"', use_shell=False)
        #result = remote('echo "standard out"; echo "sleeping"; sleep 2; >&2 echo "standard error"; exit 2', combine_stderr=False)
        #result = remote_sudo('salt-call state.highstate')
        #result = remote('foo=bar; echo "bar? $foo!"', use_shell=False)
        # read from stdin
        #result = remote('echo "> "; cat -')

        # these should all re-use the same network connection
        # (they don't, see TODO)
        command_list = [
            "echo hello,",
            "echo world.",
            "echo how",
            "echo are",
            "echo you?",
        ]
        for command in command_list:
            handle_result_1(remote(command))
            
        #print(remote_file_exists('/tmp'))
        #operations.download('/var/log/daily-logrotate.log', '/tmp/daily-logrotate.log')
        #operations.remote('rm /tmp/payload')
        #operations.upload('/tmp/payload', '/tmp/payload')
        #assert operations.remote_file_exists('/tmp/payload'), "file failed to upload"

    print('done')

if __name__ == '__main__':
    main()
