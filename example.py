import os
from functools import partial
from io import BytesIO
from threadbare import execute
from threadbare import state
from threadbare.state import settings
from threadbare.operations import (
    remote,
    remote_file_exists,
    remote_sudo,
    local,
    download,
    upload,
    single_command,
    lcd,
    rcd,
)

HOST = os.environ.get("THREADBARE_TEST_HOST")
USER = os.environ.get("THREADBARE_TEST_USER")

_help_text = """two environment variables must be defined before executing this script:
THREADBARE_TEST_HOST=yourhost
THREADBARE_TEST_USER=youruser
"""
assert HOST and USER, _help_text

test_settings = partial(settings, user=USER, host_string=HOST)


def test_nest_some_settings():
    "demonstrates how settings accumulate"
    with settings(foo="bar"):
        with settings(bar="baz"):
            with settings(baz="bup"):
                print("after three nestings I have the cumulate state: %s" % state.ENV)


def test_run_a_local_command():
    "run a simple local command"
    print(local("echo hello, world!"))


def test_run_a_local_command_with_separate_streams():
    "run a simple local command but capture the output"
    print(local("echo hello, world!", capture=True))


def test_run_a_local_command_in_a_different_dir():
    "switch to a different local directory to run a command"
    with lcd("/tmp"):
        print(local("pwd", capture=True))


def test_run_a_remote_command():
    "run a simple remote command"
    with test_settings():
        print(remote(r'echo -e "\e[31mDanger Will Robinson!\e[0m"'))


def test_run_a_remote_command_in_a_different_dir():
    "run a simple remote command in a different remote directory"
    with test_settings():
        with rcd("/tmp"):
            print(remote("pwd"))


def test_run_a_remote_command_as_root():
    "run a simple remote command as root"
    with test_settings():
        print(remote_sudo("cd /root && echo tapdance in $(pwd)"))


def test_run_a_remote_command_with_separate_streams():
    "run a simple remote command and capture stdout and stderr separately"
    with test_settings():
        print(
            remote(
                'echo "standard out"; >&2 echo "standard error"; exit 123',
                combine_stderr=False,
            )
        )


def test_run_a_remote_command_with_shell_interpolation():
    "run a simple remote command including variables"
    with test_settings():
        print(remote('foo=bar; echo "bar? $foo!"'))
        print(remote('foo=bar; echo "bar? $foo!"', use_shell=False))


def test_run_many_remote_commands():
    "running many remote commands re-uses the established ssh session"
    command_list = [
        "echo all",
        "echo these commands",
        "echo share the same",
        "echo ssh session",
    ]
    with test_settings():
        for command in command_list:
            print(remote(command))


def test_run_many_remote_commands_singly():
    "running many remote commands re-uses the established ssh session"
    command_list = [
        "echo all",
        "echo these commands",
        "echo are executed",
        "echo together",
    ]
    with test_settings():
        print(remote(single_command(command_list)))


def test_run_many_remote_commands_serially():
    pass


def test_run_many_remote_commands_in_parallel():
    pass


def _upload_a_file(local_file_name):
    local_file_contents = "foo"
    with open(local_file_name, "w") as fh:
        fh.write(local_file_contents)
    remote_file_name = "/tmp/threadbare-payload.tmp"
    upload(local_file_name, remote_file_name)
    assert remote_file_exists(remote_file_name)
    return remote_file_name


def _modify_remote_file(remote_file_name):
    remote('printf "bar" >> %s' % remote_file_name)


def _download_a_file(remote_file_name):
    new_local_file_name = "/tmp/threadbare-payload.tmp2"
    download(remote_file_name, new_local_file_name)
    remote("rm %s" % remote_file_name)
    return new_local_file_name


def _modify_local_file(local_file_name):
    local('printf "baz" >> %s' % local_file_name)


def test_upload_and_download_a_file():
    "write a local file, upload it to the remote server, modify it remotely, download it, modify it locally, assert it's contents are as expected"
    with test_settings():
        print("uploading file ...")
        local_file_name = "/tmp/threadbare-payload.tmp"
        uploaded_file = _upload_a_file(local_file_name)

        print("modifying remote file ...")
        _modify_remote_file(uploaded_file)

        print("downloading file ...")
        new_local_file_name = _download_a_file(uploaded_file)

        print("modifying local file ...")
        _modify_local_file(new_local_file_name)

        print("testing local file ...")
        data = open(new_local_file_name, "r").read()
        assert data == "foobarbaz"

        print("good!")


def test_download_file_owned_by_root():
    "a file owned by root can be downloaded by the regular user if 'use_sudo' is True"
    with test_settings():
        # create a root-only file on remote machine
        remote_file_name = "/root/threadbare-test.temp"
        file_contents = "root users only!\n"
        remote_sudo(
            single_command(
                [
                    'printf "%s" > "%s"' % (file_contents, remote_file_name),
                    'chmod 600 "%s"' % remote_file_name,
                ]
            )
        )

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
        assert open(local_file_name, "r").read() == file_contents

        # cleanup. remove remote root-only file
        remote_sudo('rm -f "%s"' % remote_file_name)


def test_upload_file_to_root_dir():
    "uploads a file as a regular user to the /root directory with `use_sudo`"
    with test_settings():
        remote_file_name = "/root/threadbare-test.temp"
        remote_sudo('rm -f "%s"' % remote_file_name)  # sanity check
        assert not remote_file_exists(remote_file_name, use_sudo=True)

        local_file_name = "/tmp/threadbare-test.temp"
        local('echo foobarbaz > "%s"' % local_file_name)
        print("uploading file (this is *very* slow over SFTP)")
        upload(local_file_name, remote_file_name, use_sudo=True)
        print("done uploading")

        assert remote_file_exists(remote_file_name, use_sudo=True)


def _upload_bytes_to_remote_file():
    unicode_buffer = BytesIO(b"foobarbaz")
    remote_file_name = "/tmp/threadbare-bytes-test.temp"
    upload(unicode_buffer, remote_file_name)
    print(remote('cat "%s"' % remote_file_name))
    return remote_file_name


def _download_file_to_local_bytes(remote_file_name):
    assert remote_file_exists(remote_file_name)
    unicode_buffer = BytesIO()
    download(remote_file_name, unicode_buffer)
    print(unicode_buffer.getvalue())


def test_upload_and_download_a_file_using_bytes():
    """contents of a BytesIO buffer can be uploaded to a remote file, 
    and the contents of a remote file can be downloaded to a BytesIO buffer"""
    with test_settings(quiet=True):
        remote_file_name = _upload_bytes_to_remote_file()
        _download_file_to_local_bytes(remote_file_name)


def test_check_remote_files():
    "check that remote files can be found (or not)"
    file_that_exists = "/var/log/syslog"
    file_that_does_not_exist = "/foo/bar"
    with test_settings():
        assert remote_file_exists(file_that_exists)
        assert not remote_file_exists(file_that_does_not_exist)


def test_check_many_remote_files():
    "checks multiple remote files for existence in parallel"

    @execute.parallel
    def workerfn():
        with state.settings() as env:
            return remote_file_exists(env["remote_file"], use_sudo=True)

    with test_settings():
        remote_file_list = [
            "/var/log/syslog",  # True, exists
            "/foo/bar",  # False, doesn't exist
        ]

        expected = [True, False]
        result = execute.execute(
            state.ENV, workerfn, param_key="remote_file", param_values=remote_file_list
        )
        assert expected == result


# see `threadbare/__init__.py` for gevent monkey patching that allows
# gevent threads (pssh), python futures (boto) and python multiprocessing (threadbare/fabric)
# to work harmoniously


def test_mix_match_ssh_clients1():
    "remote commands run serially, then in parallel, then serially don't interfere with each other"
    # main process
    test_run_a_remote_command()  # works
    # child processes
    test_check_many_remote_files()  # works with monkey_patch
    # main process again
    test_run_a_remote_command()  # works


def test_mix_match_ssh_clients2():
    "remote command run after parallel remote commands don't interfere with each other"
    # child processes
    test_check_many_remote_files()  # works
    # main process again
    test_run_a_remote_command()  # works


def test_mix_match_ssh_clients3():
    "remote commands run in parallel, then serially, then in parallel again don't interfere with each other"
    # child processes
    test_check_many_remote_files()  # works
    # main process
    test_run_a_remote_command()  # works
    # child processes
    test_check_many_remote_files()  # works with monkey_patch


def test_mix_match_ssh_clients4():
    "remote commands run in parallel after each other don't interface with each other"
    test_check_many_remote_files()  # works
    test_check_many_remote_files()  # works
