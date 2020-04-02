import pytest
import os
from functools import partial
from io import BytesIO
from threadbare import execute, state, common
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
    hide,
)
import logging

logging.basicConfig()

LOG = logging.getLogger(__name__)

HOST = os.environ.get("THREADBARE_TEST_HOST")
PORT = os.environ.get("THREADBARE_TEST_PORT")
USER = os.environ.get("THREADBARE_TEST_USER")
KEY = os.environ.get("THREADBARE_TEST_PUBKEY", None)

_help_text = """the environment variables below must be defined before executing this script:
THREADBARE_TEST_HOST=
THREADBARE_TEST_PORT=
THREADBARE_TEST_USER=
THREADBARE_TEST_PUBKEY=

and THREADBARE_TEST_PORT must be an integer.
"""
assert (HOST and PORT and USER) and common.isint(PORT), _help_text

test_settings = partial(
    settings, user=USER, port=int(PORT), host_string=HOST, key_filename=KEY
)

# local tests
# see `tests/test_state.py` and `tests/test_operations.py` for more examples


def test_nest_some_settings():
    "demonstrates how settings accumulate"
    with settings(foo="bar"):
        with settings(bar="baz"):
            with settings(baz="bup"):
                LOG.debug(
                    "after three nestings I have the cumulate state: %s" % state.ENV
                )
                assert state.ENV == {"foo": "bar", "bar": "baz", "baz": "bup"}


def test_run_a_local_command():
    "run a simple local command"
    result = local("echo hello, world!")
    assert result["succeeded"]


def test_run_a_local_command_with_separate_streams():
    "run a simple local command but capture the output"
    result = local("echo hello, world!", capture=True)
    assert result["succeeded"]


def test_run_a_local_command_in_a_different_dir():
    "switch to a different local directory to run a command"
    with lcd("/tmp"):
        result = local("pwd", capture=True)
        assert result["succeeded"]
        assert result["stdout"] == ["/tmp"]


def test_run_a_local_command_but_hide_output():
    "presumably for side effects"
    with hide():
        result = local("cat /etc/passwd", capture=False)
        # (nothing should be emitted)
        assert result["succeeded"]
        assert result["stdout"] == []
        assert result["stderr"] == []


def test_run_many_local_commands_serially():
    "run a list of commands serially. `serial` exists to complement `parallel`"
    command_list = [
        "echo all",
        "echo these commands",
        "echo are executed",
        "echo in serially",
    ]

    def myfn():
        return local(state.ENV["cmd"], capture=True)

    results = execute.execute(myfn, param_key="cmd", param_values=command_list)
    assert len(results) == len(command_list)
    assert results[-2]["stdout"][0] == "are executed"


def test_run_many_local_commands_in_parallel():
    "run a set of commands in parallel using Python's multiprocessing"
    command_list = [
        "echo all",
        "echo these commands",
        "echo are executed",
        "echo in parallel",
    ]

    @execute.parallel
    def myfn():
        return local(state.ENV["cmd"], capture=True)

    results = execute.execute(myfn, param_key="cmd", param_values=command_list)
    assert len(results) == len(command_list)
    assert results[-2]["stdout"][0] == "are executed"


# remote tests


def test_run_a_remote_command():
    "run a simple `remote` command"
    with test_settings(quiet=True):
        result = remote(r'echo -e "\e[31mRed Text!!\e[0m"')
        assert result["succeeded"]


def test_run_a_remote_command_in_a_different_dir():
    "run a simple `remote` command in a different remote directory"
    with test_settings():
        with rcd("/tmp"):
            result = remote("pwd")
            assert result["succeeded"]


def test_run_a_remote_command_but_hide_output():
    "run a simple `remote` command but don't print anything"
    with test_settings():
        with hide():
            result = remote("echo hi!")
            # (nothing should have been emitted)
            assert result["succeeded"]
            assert result["stdout"] == ["hi!"]


def test_run_a_remote_command_as_root():
    "run a simple `remote` command as the root user"
    with test_settings():
        result = remote_sudo("cd /root && echo tapdance in $(pwd)")
        assert result["succeeded"]


def test_run_a_remote_command_with_separate_streams():
    "run a simple `remote` command and capture stdout and stderr separately"
    with test_settings():
        result = remote(
            'echo "standard out"; >&2 echo "standard error"', combine_stderr=False,
        )
        assert result["succeeded"]
        assert result["stdout"] == ["standard out"]
        assert result["stderr"] == ["standard error"]


def test_run_a_remote_command_with_shell_interpolation():
    "run a simple `remote` command including variables"
    with test_settings(quiet=True):
        assert remote('foo=bar; echo "bar? $foo!"')["succeeded"]
        assert remote('foo=bar; echo "bar? $foo!"', use_shell=False)["succeeded"]


def test_run_a_remote_command_non_zero_return_code():
    """`remote` commands, like `local` commands, will raise a RuntimeError if the command they execute fails.
    the results of the command are still available via the `result` attribute on the exception object"""
    with test_settings():
        with pytest.raises(RuntimeError) as err:
            remote("exit 123")
        exc = err.value
        assert exc.result["return_code"] == 123
        assert exc.result["failed"]
        assert not exc.result["succeeded"]


def test_run_a_remote_command_non_zero_custom_exit():
    """`remote` commands, like `local` commands, may raise a custom exception if the command they execute fails.
    the results of the command are still available via the `result` attribute on the exception object"""
    with test_settings():
        with pytest.raises(ValueError) as err:
            remote("exit 123", abort_exception=ValueError)
        exc = err.value
        assert exc.result["return_code"] == 123
        assert exc.result["failed"]
        assert not exc.result["succeeded"]


def test_run_a_remote_command_non_zero_return_code_swallow_error():
    "`remote` commands, like `local` commands, can return the results of failed executions when `warn_only` is `True`"
    with test_settings(warn_only=True):
        result = remote("exit 123")
        assert result["return_code"] == 123
        assert result["failed"]
        assert not result["succeeded"]


def test_run_many_remote_commands():
    "running many `remote` commands re-uses the established ssh session"
    command_list = [
        "echo all",
        "echo these commands",
        "echo share the same",
        "echo ssh session",
    ]
    with test_settings():
        for command in command_list:
            result = remote(command)
            assert result["succeeded"]


def test_run_many_remote_commands_singly():
    "running many `remote` commands re-uses the established ssh session"
    command_list = [
        "echo all",
        "echo these commands",
        "echo are executed",
        "echo together",
    ]
    with test_settings():
        result = remote(single_command(command_list))
        assert result["succeeded"]


def test_run_many_remote_commands_serially():
    """run a list of `remote` commands serially. `remote` commands run serially 
    with `execute` do not share a ssh connection (at time of writing)
    TODO: investigate above statement. explain why
    """
    command_list = [
        "echo all",
        "echo these commands",
        "echo are executed",
        "echo serially and remotely",
    ]

    def myfn():
        return remote(state.ENV["cmd"], capture=True)

    with test_settings():
        results = execute.execute(myfn, param_key="cmd", param_values=command_list)
        assert len(results) == len(command_list)
        assert results[-2]["stdout"][0] == "are executed"


def test_run_many_remote_commands_in_parallel():
    """run a list of `remote` commands in parallel. 
    `remote` commands run in parallel do not share a ssh connection.
    the order of results can be guaranteed but not the order in which output is emitted"""
    command_list = [
        "echo all",
        "echo these commands",
        "echo are executed",
        "echo remotely and in parallel",
    ]

    @execute.parallel
    def myfn():
        return remote(state.ENV["cmd"], capture=True)

    with test_settings(quiet=True):
        results = execute.execute(myfn, param_key="cmd", param_values=command_list)
        assert len(results) == len(command_list)
        assert results[-2]["stdout"][0] == "are executed"


def test_remote_exceptions_in_parallel():
    """remote commands that raise exceptions while running in parallel have the exception 
    object returned to the them as the result"""

    def workerfn():
        with state.settings():
            return remote("exit 1")

    workerfn = execute.parallel(workerfn, pool_size=1)

    with test_settings():
        expected = RuntimeError(
            "remote() encountered an error (return code 1) while executing '/bin/bash -l -c \"exit 1\"'"
        )
        result_list = execute.execute(workerfn)
        result = result_list[0]
        assert str(expected) == str(result)


def _upload_a_file(local_file_name):
    local_file_contents = "foo"
    with open(local_file_name, "w") as fh:
        fh.write(local_file_contents)
    remote_file_name = "/tmp/threadbare-payload.tmp1"
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
        LOG.debug("uploading file ...")
        local_file_name = "/tmp/threadbare-payload.tmp"
        uploaded_file = _upload_a_file(local_file_name)

        LOG.debug("modifying remote file ...")
        _modify_remote_file(uploaded_file)

        LOG.debug("downloading file ...")
        new_local_file_name = _download_a_file(uploaded_file)

        LOG.debug("modifying local file ...")
        _modify_local_file(new_local_file_name)

        LOG.debug("testing local file ...")
        data = open(new_local_file_name, "r").read()
        assert data == "foobarbaz"


def test_upload_and_download_a_file_using_sftp():
    "same as `test_upload_and_download_a_file`, but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        test_upload_and_download_a_file()


def test_upload_a_directory():  # you can't
    "attempting to upload a directory raises an exception"
    with test_settings():
        try:
            upload("/tmp", "/tmp")
            assert False, "you shouldn't be able to upload a directory!"
        except ValueError:
            pass


def test_upload_a_directory_using_sftp():  # you still can't
    with settings(transfer_protocol="sftp"):
        test_upload_a_directory()


def test_download_a_directory():  # you can't
    """attempting to download a directory raises an exception.
    It's possible, both parallel-ssh and paramiko use SFTP, but not supported."""
    with test_settings():
        try:
            download("/tmp", "/tmp")
            assert False, "you shouldn't be able to download a directory!"
        except ValueError:
            pass


def test_download_a_directory_using_sftp():  # you still can't
    with settings(transfer_protocol="sftp"):
        test_download_a_directory()


def test_download_an_obvious_directory():  # you can't
    """attempting to download an obvious directory raises an exception.
    It's possible, both parallel-ssh and paramiko use SFTP, but not supported."""
    with test_settings():
        try:
            download("/tmp/", "/tmp")
            assert False, "you shouldn't be able to download a directory!"
        except ValueError:
            pass


def test_download_an_obvious_directory_using_sftp():  # you still can't
    with settings(transfer_protocol="sftp"):
        test_download_an_obvious_directory()


def test_download_a_file_to_a_directory():
    """a file can be downloaded to a directory and the name of the remote file will be used as the destination file"""
    with test_settings():
        local_dir = "/tmp"
        remote_file = "/bin/less"
        expected_local_file = "/tmp/less"
        try:
            new_local_file = download(remote_file, local_dir)
            assert expected_local_file == new_local_file
            assert os.path.exists(expected_local_file)
        finally:
            local('rm -f "%s"' % expected_local_file)


def test_download_a_file_to_a_directory_using_sftp():
    "same as `test_download_a_file_to_a_directory` but using SFTP"
    with settings(transfer_protocol="sftp"):
        test_download_a_file_to_a_directory()


def test_download_a_file_to_a_relative_directory():
    "relative destinations are expanded to full paths before downloading"
    with test_settings():
        with lcd("/tmp"):
            try:
                expected_local_file = "/tmp/less"
                new_local_file = download("/bin/less", ".")
                assert expected_local_file == new_local_file
                assert os.path.exists(expected_local_file)
            finally:
                local('rm -f "%s"' % expected_local_file)


def test_download_a_file_to_a_relative_directory_using_sftp():
    with settings(transfer_protocol="sftp"):
        test_download_a_file_to_a_relative_directory()


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


def test_download_file_owned_by_root_using_sftp():
    with settings(transfer_protocol="sftp"):
        test_download_file_owned_by_root()


def test_upload_file_to_root_dir():
    "uploads a file as a regular user to the /root directory with `use_sudo`"
    with test_settings():
        remote_file_name = "/root/threadbare-test.temp"
        remote_sudo('rm -f "%s"' % remote_file_name)  # sanity check
        assert not remote_file_exists(remote_file_name, use_sudo=True)

        local_file_name = "/tmp/threadbare-test.temp"
        local('echo foobarbaz > "%s"' % local_file_name)
        LOG.debug("uploading file (this is *very* slow over SFTP)")
        upload(local_file_name, remote_file_name, use_sudo=True)
        LOG.debug("done uploading")

        assert remote_file_exists(remote_file_name, use_sudo=True)


def test_upload_file_to_root_dir_using_sftp():
    with settings(transfer_protocol="sftp"):
        test_upload_file_to_root_dir()


def test_upload_and_download_a_file_using_byte_buffers():
    """contents of a BytesIO buffer can be uploaded to a remote file, 
    and the contents of a remote file can be downloaded to a BytesIO buffer"""
    with test_settings(quiet=True):
        payload = b"foobarbaz"

        uploadable_unicode_buffer = BytesIO(payload)
        remote_file_name = "/tmp/threadbare-bytes-test.temp"
        upload(uploadable_unicode_buffer, remote_file_name)

        assert remote_file_exists(remote_file_name)
        result = remote('cat "%s"' % remote_file_name)
        assert result["succeeded"]
        assert result["stdout"][0] == payload.decode()

        download_unicode_buffer = BytesIO()
        download(remote_file_name, download_unicode_buffer)
        assert download_unicode_buffer.getvalue() == payload


def test_upload_and_download_a_file_using_byte_buffers_and_sftp():
    with settings(transfer_protocol="sftp"):
        test_upload_and_download_a_file_using_byte_buffers()


def test_check_remote_files():
    "check that remote files can be found (or not)"
    file_that_exists = "/var/log/wtmp"  # login/logout entries (see `man last`)
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
            "/var/log/wtmp",  # True, exists
            "/foo/bar",  # False, doesn't exist
        ]

        expected = [True, False]
        result = execute.execute(
            workerfn, param_key="remote_file", param_values=remote_file_list
        )
        assert expected == result


def test_line_formatting():
    # todo: not a great test. how do I capture and test the formatted line while preserving the original output?
    num_workers = 2

    @execute.parallel
    def workerfn():
        iterations = 2
        cmd = 'for run in {1..%s}; do echo "I am %s, iteration $run"; done' % (
            iterations,
            state.ENV["worker_num"],
        )
        return remote(cmd)

    expected = [
        {
            "command": '/bin/bash -l -c "for run in {1..2}; do echo \\"I am 1, iteration \\$run\\"; done"',
            "failed": False,
            "return_code": 0,
            "stderr": [],
            "stdout": ["I am 1, iteration 1", "I am 1, iteration 2",],
            "succeeded": True,
        },
        {
            "command": '/bin/bash -l -c "for run in {1..2}; do echo \\"I am 2, iteration \\$run\\"; done"',
            "failed": False,
            "return_code": 0,
            "stderr": [],
            "stdout": ["I am 2, iteration 1", "I am 2, iteration 2"],
            "succeeded": True,
        },
    ]

    with test_settings(line_template="[{host}] {pipe}: {line}\n"):
        results = execute.execute(
            workerfn,
            param_key="worker_num",
            param_values=list(range(1, num_workers + 1)),
        )
    assert expected == results


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
