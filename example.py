import contextlib
import pytest
import os, shutil, tempfile
from os.path import join, basename
from functools import partial
from io import BytesIO
from threadbare import execute, state, common, operations
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

HOST = "localhost"
PORT = os.environ.get("THREADBARE_TEST_PORT")
USER = os.environ.get("THREADBARE_TEST_USER")
KEY = os.environ.get("THREADBARE_TEST_PUBKEY", None)

_help_text = """the environment variables below must be defined before executing this script:
THREADBARE_TEST_PORT=
THREADBARE_TEST_USER=
THREADBARE_TEST_PUBKEY=

THREADBARE_TEST_PORT must be an integer.

It's assumed the dummy sshd server is running and that the host is `localhost`.
"""
assert (HOST and PORT and USER) and common.isint(PORT), _help_text

test_settings = partial(
    settings, user=USER, port=int(PORT), host_string=HOST, key_filename=KEY
)


def _env_fixture(prefix):
    """creates a temporary directory with three files in it, 'small-file', 'medium-file' and 'large-file'.
    the paths to the directory and files are yielded as a map and then all is removed afterwards."""

    @contextlib.contextmanager
    def wrapper():
        tempdir = tempfile.mkdtemp(prefix="threadbare-" + prefix)

        # create some empty files of specific sizes
        path_map = {
            "small-file": join(tempdir, "small-file.temp"),
            "medium-file": join(tempdir, "medium-file.temp"),
            # "large-file": join(tempdir, "large-file.temp") # unused
        }
        file_size_map = {
            "small-file": "1KiB",
            "medium-file": "1MiB",
            "large-file": "25MiB",
        }
        for path_name, path in path_map.items():
            file_size = file_size_map[path_name]
            local("fallocate -l %s %s" % (file_size, path))

        try:
            yield {"temp-dir": tempdir, "temp-files": path_map}
        finally:
            # permissions on temp dir may have changed. make sure we can still remove it.
            local('chown %s:%s -R "%s"' % (USER, USER, tempdir), use_sudo=True)
            shutil.rmtree(tempdir)

    return wrapper


def _empty_env_fixture(prefix):
    "creates a temporary directory with no files in it, yields the directory name and cleans itself up afterwards."

    @contextlib.contextmanager
    def wrapper():
        tempdir = tempfile.mkdtemp(prefix="threadbare-" + prefix)
        try:
            yield {"temp-dir": tempdir}
        finally:
            # permissions on temp dir may have changed. make sure we can still remove it.
            local('chown %s:%s -R "%s"' % (USER, USER, tempdir), use_sudo=True)
            shutil.rmtree(tempdir)

    return wrapper


# pytest fixtures turned out to be too brittle and too magical. I'd rather nested context managers.
# remote_env = pytest.fixture(_env("remote"))
# local_env = pytest.fixture(_env("local"))
# empty_local_env = pytest.fixture(_empty_env("local"))
# empty_remote_env = pytest.fixture(_empty_env("remote"))

# remote and local are the same but lets pretend they're not.
empty_local_fixture = _empty_env_fixture("local")
empty_remote_fixture = _empty_env_fixture("remote")
local_fixture = _env_fixture("local")
remote_fixture = _env_fixture("remote")


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
    assert results[-2]["stdout"] == ["are executed"]


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
    assert results[-2]["stdout"] == ["are executed"]


# remote tests
# these assume the dummy sshd server (configured in `./tests-remote/sshd-server.sh`) is being
# run and that both local and remote are the same machine.


def test_run_a_remote_command():
    "run a simple `remote` command"
    with test_settings(quiet=True):
        result = remote(r'echo -e "\e[31mRed Text!!\e[0m"')
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


def test_run_a_remote_command_in_a_different_dir():
    "run a simple `remote` command in a different remote directory"
    with remote_fixture() as remote_env:
        with test_settings():
            remote_dir = remote_env["temp-dir"]
            with rcd(remote_dir):
                result = remote("pwd")
    assert result["succeeded"]
    assert [remote_dir] == result["stdout"]


def test_run_a_remote_command_with_separate_streams():
    "run a simple `remote` command and capture stdout and stderr separately"
    with test_settings():
        result = remote(
            'echo "printed to standard out"; >&2 echo "printed to standard error"',
            combine_stderr=False,
        )
        assert result["succeeded"]
        assert ["printed to standard out"] == result["stdout"]
        assert ["printed to standard error"] == result["stderr"]


def test_run_a_remote_command_with_shell_interpolation():
    "run a simple `remote` command including shell variables"
    with test_settings(quiet=True):
        result = remote('foo=baz; echo "bar? $foo!"')
        assert result["succeeded"]
        assert ["bar? baz!"] == result["stdout"]

        result2 = remote('foo=baz; echo "bar? $foo!"', use_shell=False)
        assert result2["succeeded"]
        assert ["bar? baz!"] == result["stdout"]


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
    "multiple commands can be concatenated into a single command"
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
    """run a list of `remote` commands serially. The `execute` module is aimed at 
    running commands in parallel. 
    Serial execution exists only as a sensible default and offers nothing extra."""
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
        assert results[-2]["stdout"] == ["are executed"]


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
        assert results[-2]["stdout"] == ["are executed"]


def test_remote_exceptions_in_parallel():
    """Remote commands that raise exceptions while executing in parallel return the exception object."""

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


def test_check_remote_files():
    "check that remote files can be found (or not)"
    with remote_fixture() as remote_env:
        with test_settings():
            file_that_exists = join(remote_env["temp-files"]["small-file"])
            file_that_does_not_exist = join(remote_env["temp-dir"], "doesnot.exist")
            assert remote_file_exists(file_that_exists)
            assert not remote_file_exists(file_that_does_not_exist)


def test_upload_and_download_a_file():
    """write a local file, upload it to the remote server, modify it remotely, download it, modify it locally, 
    assert it's contents are as expected"""
    with empty_local_fixture() as local_env:
        with empty_remote_fixture() as remote_env:
            with test_settings():
                LOG.debug("modifying local file ...")
                local_file_name = join(local_env["temp-dir"], "foo")
                local('printf "foo" > %s' % local_file_name)

                LOG.debug("uploading file ...")
                remote_file_name = join(remote_env["temp-dir"], "foobar")
                upload(local_file_name, remote_file_name)
                # verify contents
                assert remote_file_exists(remote_file_name)

                assert remote("cat %s" % remote_file_name)["stdout"] == ["foo"]

                LOG.debug("modifying remote file ...")
                remote('printf "bar" >> %s' % remote_file_name)
                # verify contents
                assert remote("cat %s" % remote_file_name)["stdout"] == ["foobar"]

                LOG.debug("downloading file ...")
                new_local_file_name = join(local_env["temp-dir"], "foobarbaz")
                download(remote_file_name, new_local_file_name)
                # verify contents
                assert open(new_local_file_name, "r").read() == "foobar"

                LOG.debug("modifying local file (again) ...")
                local('printf "baz" >> %s' % new_local_file_name)

                LOG.debug("testing local file ...")
                data = open(new_local_file_name, "r").read()
                assert "foobarbaz" == data


def test_upload_and_download_a_file_using_sftp():
    "same as `test_upload_and_download_a_file`, but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        return test_upload_and_download_a_file()


def test_upload_a_directory():  # you can't
    "attempting to upload a directory raises an exception"
    with empty_local_fixture() as local_env:
        with empty_remote_fixture() as remote_env:
            with test_settings():
                with pytest.raises(ValueError):
                    upload(local_env["temp-dir"], remote_env["temp-dir"])


def test_upload_a_directory_using_sftp():  # you still can't
    "same as `test_upload_a_directory` but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        test_upload_a_directory()


def test_upload_to_extant_remote_file():
    "the default policy is to overwrite files that exist."
    with empty_local_fixture():
        with remote_fixture() as remote_env:
            with test_settings():
                payload = b"foo"
                remote_file = remote_env["temp-files"]["small-file"]

                # just to illustrate an overwrite *is* happening
                assert remote_file_exists(remote_file)
                upload(BytesIO(payload), remote_file)
                result = remote('cat "%s"' % (remote_file,))
                assert [payload.decode("utf-8")] == result["stdout"]


def test_upload_to_extant_remote_file_using_sftp():
    "same as `test_upload_to_extant_remote_file` but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        test_upload_to_extant_remote_file()


def test_upload_to_extant_remote_file_no_overwrite():
    "The default policy of overwriting files can be disabled when `override` is set to `False`."
    with empty_local_fixture():
        with remote_fixture() as remote_env:
            with test_settings():
                payload = b"foo"
                remote_file = remote_env["temp-files"]["small-file"]
                assert remote_file_exists(remote_file)
                with pytest.raises(operations.NetworkError) as exc_info:
                    upload(BytesIO(payload), remote_file, overwrite=False)

                expected_msg = (
                    "Remote file exists and 'overwrite' is set to 'False'. Refusing to write: %s"
                    % (remote_file,)
                )
                assert expected_msg == str(exc_info.value)


def test_upload_to_extant_remote_file_no_overwrite_using_sftp():
    "same as `test_upload_to_extant_remote_file_no_overwrite` but using SFTP to transfer files."
    with settings(transfer_protocol="sftp"):
        test_upload_to_extant_remote_file_no_overwrite()


def test_download_to_extant_local_file():
    "the default policy is to overwrite files that exist."
    with local_fixture() as local_env:
        with empty_remote_fixture() as remote_env:
            with test_settings():
                local_file = local_env["temp-files"]["small-file"]
                assert os.path.exists(local_file)

                payload = "foo"
                remote_file = join(remote_env["temp-dir"], "foo.file")
                remote('printf %s > "%s"' % (payload, remote_file))
                assert remote_file_exists(remote_file)

                download(remote_file, local_file)
                result = open(local_file, "r").read()
                assert payload == result


def test_download_to_extant_local_file_using_sftp():
    "same as `test_download_to_extant_local_file` but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        test_download_to_extant_local_file()


def test_download_to_extant_local_file_no_overwrite():
    "the default policy of overwriting files can be disabled when `override` is set to `False`."
    with local_fixture() as local_env:
        with remote_fixture() as remote_env:
            with test_settings():
                local_file = local_env["temp-files"]["small-file"]
                remote_file = remote_env["temp-files"]["medium-file"]

                with pytest.raises(operations.NetworkError) as exc_info:
                    download(remote_file, local_file, overwrite=False)

                expected_msg = (
                    "Local file exists and 'overwrite' is set to 'False'. Refusing to write: %s"
                    % (local_file,)
                )
                assert expected_msg == str(exc_info.value)


def test_download_to_extant_local_file_no_overwrite_using_sftp():
    "same as `test_download_to_extant_local_file_no_overwrite` but using SFTP to transfer files."
    with settings(transfer_protocol="sftp"):
        test_download_to_extant_local_file_no_overwrite()


def test_download_a_directory():  # you can't
    "attempting to download a directory raises an exception."
    # its possible as both parallel-ssh and paramiko use SFTP, but unsupported in threadbare.
    with empty_local_fixture() as local_env:
        with empty_remote_fixture() as remote_env:
            with test_settings():
                # it becomes ambiguous if remote path is a file or a directory
                remote_dir = remote_env["temp-dir"]
                assert not remote_dir.endswith("/")
                with pytest.raises(ValueError):
                    download(remote_dir, local_env["temp-dir"])


def test_download_a_directory_using_sftp():  # you still can't
    "same as `test_download_a_directory` but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        test_download_a_directory()


def test_download_an_obvious_directory():  # you can't
    """attempting to download an obvious directory (trailing slash /) raises an exception.
    Its possible as both parallel-ssh and paramiko use SFTP, but not supported."""
    with empty_local_fixture() as local_env:
        with empty_remote_fixture() as remote_env:
            with test_settings():
                # ensure we're dealing with an obvious directory
                remote_dir = "%s/" % remote_env["temp-dir"].rstrip("/")
                with pytest.raises(ValueError):
                    download(remote_dir, local_env["temp-dir"])


def test_download_an_obvious_directory_using_sftp():  # you still can't
    "same as `test_download_an_obvious_directory` but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        test_download_an_obvious_directory()


def test_download_a_file_to_a_directory():
    "a file can be downloaded to a directory and the name of the remote file will be used as the destination file"
    with empty_local_fixture() as local_env:
        with remote_fixture() as remote_env:
            with test_settings():
                local_dir = local_env["temp-dir"]
                remote_file = remote_env["temp-files"]["small-file"]
                expected_local_file = join(local_dir, basename(remote_file))

                new_local_file = download(remote_file, local_dir)
                assert os.path.exists(expected_local_file)
                assert expected_local_file == new_local_file


def test_download_a_file_to_a_directory_using_sftp():
    "same as `test_download_a_file_to_a_directory` but using SFTP"
    with settings(transfer_protocol="sftp"):
        test_download_a_file_to_a_directory()


def test_download_a_file_to_a_relative_directory():
    "relative destinations are expanded to full paths before downloading"
    with remote_fixture() as remote_env:
        with empty_local_fixture() as local_env:
            with test_settings():
                with lcd(local_env["temp-dir"]):
                    remote_file = remote_env["temp-files"]["small-file"]
                    expected_local_file = join(
                        local_env["temp-dir"], basename(remote_file)
                    )

                    new_local_file = download(remote_file, ".")
                    assert expected_local_file == new_local_file
                    assert os.path.exists(expected_local_file)


def test_download_a_file_to_a_relative_directory_using_sftp():
    "same as `test_download_a_file_to_a_relative_directory` but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        test_download_a_file_to_a_relative_directory()


def test_download_file_owned_by_root():
    "a file owned by root can be downloaded by the regular user if 'use_sudo' is True"
    with empty_local_fixture() as local_env:
        with remote_fixture() as remote_env:
            with test_settings():
                # create a root-only file on remote machine
                remote_file_name = remote_env["temp-files"]["small-file"]
                file_contents = "root users only!\n"
                remote_sudo('printf "%s" > "%s"' % (file_contents, remote_file_name))
                remote_sudo('chmod 600 "%s"' % remote_file_name)
                remote_sudo('chown root:root "%s"' % remote_file_name)

                local_file_name = join(
                    local_env["temp-dir"], basename(remote_file_name)
                )

                # ensure remote root-only file cannot be downloaded by regular user.
                # in this case we own the directory but the file is owned by root.
                with pytest.raises(operations.NetworkError):
                    download(remote_file_name, local_file_name)

                # download remote root-only file as regular user
                download(remote_file_name, local_file_name, use_sudo=True)
                assert os.path.exists(local_file_name)
                assert file_contents == open(local_file_name, "r").read()


def test_download_file_owned_by_root_using_sftp():
    "same as `test_download_file_owned_by_root` but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        test_download_file_owned_by_root()


def test_upload_file_to_root_dir():
    "uploads a file as a regular user to a root-owned directory with `use_sudo`"
    with local_fixture() as local_env:
        with empty_remote_fixture() as remote_env:
            with test_settings():
                remote_sudo('chown root:root -R "%s"' % remote_env["temp-dir"])

                local_file_name = local_env["temp-files"]["small-file"]
                remote_file_name = join(
                    remote_env["temp-dir"], basename(local_file_name)
                )

                # upload file to root-owned directory
                with pytest.raises(operations.NetworkError):
                    upload(local_file_name, remote_file_name)

                upload(local_file_name, remote_file_name, use_sudo=True)
                assert remote_file_exists(remote_file_name, use_sudo=True)


def test_upload_file_to_root_dir_using_sftp():
    "same as `test_upload_file_to_root_dir` but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        LOG.debug("(this is *very* slow over SFTP)")
        test_upload_file_to_root_dir()


def test_upload_and_download_a_file_using_byte_buffers():
    """contents of a BytesIO buffer can be uploaded to a remote file, 
    and the contents of a remote file can be downloaded to a BytesIO buffer"""
    with empty_remote_fixture() as remote_env:
        with test_settings(quiet=True):
            payload = b"foo-bar-baz"
            uploadable_unicode_buffer = BytesIO(payload)
            remote_file_name = join(remote_env["temp-dir"], "bytes-test")

            upload(uploadable_unicode_buffer, remote_file_name)
            assert remote_file_exists(remote_file_name)

            result = remote('cat "%s"' % remote_file_name)
            assert result["succeeded"]
            assert result["stdout"] == [payload.decode()]

            download_unicode_buffer = BytesIO()
            download(remote_file_name, download_unicode_buffer)
            assert download_unicode_buffer.getvalue() == payload


def test_upload_and_download_a_file_using_byte_buffers_and_sftp():
    "same as `test_upload_and_download_a_file_using_byte_buffers` but using SFTP to transfer files"
    with settings(transfer_protocol="sftp"):
        test_upload_and_download_a_file_using_byte_buffers()


def test_check_many_remote_files():
    "checks multiple remote files for existence in parallel"

    @execute.parallel
    def workerfn():
        with state.settings() as env:
            return remote_file_exists(env["remote_file"], use_sudo=True)

    with remote_fixture() as remote_env:
        remote_file_list = [
            remote_env["temp-files"]["small-file"],  # True, exists
            join(remote_env["temp-dir"], "doesnot.exist"),  # False, doesn't exist
        ]

        expected = [True, False]
        with test_settings():
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


# todo: patch process_status and replicate a worker 'hanging'

# todo: check output
def test_run_script():
    "a simple bash script can be uploaded and executed and the results accessible"
    with empty_local_fixture() as local_env:
        with empty_remote_fixture() as remote_env:
            with test_settings():
                local_script = join(local_env["temp-dir"], "script.sh")
                local_script_data = r"""#!/bin/bash
python -c "for n in range(0,1000):
    print(n,'foo ' * 80)"
"""
                open(local_script, "w").write(local_script_data)
                remote_script = join(remote_env["temp-dir"], "script.sh")
                upload(local_script, remote_script)
                remote("chmod +x %s" % remote_script)
                remote(
                    "cd %s && ./script.sh" % (os.path.dirname(remote_script),),
                    timeout=5,
                )


# todo: check output, run 'bar' on a second thread
def test_run_script_parallel():
    "a simple bash script can be uploaded and executed in parallel, with each of the results accessible"
    with empty_local_fixture() as local_env:
        with empty_remote_fixture() as remote_env:
            with test_settings():
                local_script = join(local_env["temp-dir"], "script.sh")
                local_script_data = r"""#!/bin/bash
python -c "for n in range(0,1000):
    print(n,'foo ' * 80)"
"""
                open(local_script, "w").write(local_script_data)
                remote_script = join(remote_env["temp-dir"], "script.sh")

                @execute.parallel
                def workerfn():
                    upload(local_script, remote_script)
                    remote("chmod +x %s" % remote_script)
                    return remote(
                        "cd %s && ./script.sh" % (os.path.dirname(remote_script),)
                    )

                print(execute.execute_with_hosts(workerfn, hosts=["127.0.0.1"]))
