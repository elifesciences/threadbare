try:
    # py3
    import unittest.mock as mock
    from unittest.mock import patch
    from io import StringIO
except ImportError:
    import mock
    from mock import patch
    from StringIO import StringIO

import pytest
from threadbare import operations, state
from threadbare.common import merge, cwd, PromptedException
from pssh import exceptions as pssh_exceptions

# remote

HOST = "testhost"
USER = "testuser"
PORT = 666
PEM = "/home/testuser/.ssh/id_rsa"


def test_hide():
    "`hide` in threadbare just sets quiet=True. It's much more fine grained in fabric."
    with operations.hide():
        assert state.ENV == {"quiet": True}


def test_hide_w_args():
    "`hide` in threadbare supports arguments for the types of things to be hidden, all of which are ignored"
    with operations.hide("egg"):
        assert state.ENV == {"quiet": True}


def test_rcd():
    "`operations.rcd` causes the command to be executed to happen in a different directory"
    with patch("threadbare.operations._execute") as mockobj:
        with operations.rcd("/tmp"):
            mockobj.return_value = {
                "return_code": lambda: 0,
                "stdout": [],
                "stderr": [],
            }
            operations.remote(
                "pwd", host_string=HOST, port=PORT, user=USER, key_filename=PEM
            )

    expected_kwargs = {
        "host_string": HOST,
        "port": PORT,
        "user": USER,
        "key_filename": PEM,
        "use_pty": True,
        "timeout": None,
        "command": '/bin/bash -l -c "cd \\"/tmp\\" && pwd"',
    }
    mockobj.assert_called_with(**expected_kwargs)


def test__ssh_client():
    "the SSHClient object factory is creating objects as expected"
    with patch("threadbare.operations.SSHClient") as m:
        operations._ssh_client(
            user="joe",
            host_string="localhost",
            key_filename="/foo/bar/baz.pem",
            port=123,
        )

    expected_initialised_with = {
        "user": "joe",
        "pkey": "/foo/bar/baz.pem",
        "host": "localhost",
        "port": 123,
        "password": None,
    }
    m.assert_called_with(**expected_initialised_with)


def test_stateful__ssh_client():
    "the SSHClient object factory is creating objects (or not) as expected"
    with state.settings():
        with patch("threadbare.operations.SSHClient") as m1:
            operations._ssh_client(
                user="joe",
                host_string="localhost",
                key_filename="/foo/bar/baz.pem",
                port=123,
            )
            expected_initialised_with = {
                "user": "joe",
                "pkey": "/foo/bar/baz.pem",
                "host": "localhost",
                "port": 123,
                "password": None,
            }
            m1.assert_called_with(**expected_initialised_with)

        with patch("threadbare.operations.SSHClient") as m2:
            operations._ssh_client(
                user="joe",
                host_string="localhost",
                key_filename="/foo/bar/baz.pem",
                port=123,
            )
            m2.assert_not_called()


def test_remote_args_to_execute():
    "`operations.remote` calls `operations._execute` with the correct arguments"
    with patch("threadbare.operations._execute") as mockobj:
        mockobj.return_value = {"return_code": lambda: 0, "stdout": [], "stderr": []}
        operations.remote(
            "echo hello", host_string=HOST, port=PORT, user=USER, key_filename=PEM
        )

    expected_kwargs = {
        "host_string": HOST,
        "port": PORT,
        "user": USER,
        "key_filename": PEM,
        "use_pty": True,
        "timeout": None,
        "command": '/bin/bash -l -c "echo hello"',
    }
    mockobj.assert_called_with(**expected_kwargs)


def test_remote_sudo_args_to_execute():
    "`operations.remote_sudo` calls `operations._execute` with the correct arguments"
    with patch("threadbare.operations._execute") as mockobj:
        mockobj.return_value = {"return_code": lambda: 0, "stdout": [], "stderr": []}
        operations.remote_sudo(
            "echo hello", host_string=HOST, port=PORT, user=USER, key_filename=PEM
        )

    expected_kwargs = {
        "host_string": HOST,
        "port": PORT,
        "user": USER,
        "key_filename": PEM,
        "use_pty": True,
        "timeout": None,
        "command": 'sudo --non-interactive /bin/bash -l -c "echo hello"',
    }
    mockobj.assert_called_with(**expected_kwargs)


# remote calls with non-default args


def test_remote_non_default_args():
    "`operations.remote` calls `operations._execute` with the correct arguments"
    base = {
        "host_string": HOST,
        "port": PORT,
        "user": USER,
        "key_filename": PEM,
        "command": "echo hello",
        "timeout": None,
    }

    # given args, expected args
    cases = [
        # non-shell regular command
        [{"use_shell": False}, {"use_pty": True, "command": "echo hello"}],
        # non-shell, non-tty command
        [
            {"use_shell": False, "combine_stderr": False},
            {"use_pty": False, "command": "echo hello"},
        ],
        # non-shell sudo command
        [
            {"use_shell": False, "use_sudo": True},
            {"use_pty": True, "command": "sudo --non-interactive echo hello"},
        ],
        # shell, regular command
        [
            {"use_shell": True},
            {"use_pty": True, "command": '/bin/bash -l -c "echo hello"'},
        ],
        # shell, sudo command
        [
            {"use_shell": True, "use_sudo": True},
            {
                "use_pty": True,
                "command": 'sudo --non-interactive /bin/bash -l -c "echo hello"',
            },
        ],
        # shell escaped operations
        [
            {"command": 'foo=bar; echo "bar? $foo!"'},
            {
                "use_pty": True,
                "command": '/bin/bash -l -c "foo=bar; echo \\"bar? \\$foo!\\""',
            },
        ],
        # shell escaped operations, non-shell
        [
            {"command": 'foo=bar; echo "bar? $foo!"', "use_shell": False},
            {"use_pty": True, "command": 'foo=bar; echo "bar? $foo!"'},
        ],
        # specific directory
        [
            {"remote_working_dir": "/tmp", "command": "pwd", "use_shell": False},
            {"use_pty": True, "command": 'cd "/tmp" && pwd'},
        ],
        [
            {"remote_working_dir": "/tmp", "command": "pwd", "use_shell": True},
            {"use_pty": True, "command": '/bin/bash -l -c "cd \\"/tmp\\" && pwd"'},
        ],
        # timeout
        [
            {"command": "sleep 5", "timeout": 1},
            {"use_pty": True, "command": '/bin/bash -l -c "sleep 5"', "timeout": 1},
        ],
        # edge cases
        # shell, non-tty command
        # in order to combine output streams, `pty` must be off
        [
            {"use_pty": False},
            {"use_pty": True, "command": '/bin/bash -l -c "echo hello"'},  # !!
        ],
        # if you really need a `pty`, you'll have to handle separate stdout/stderr streams
        [
            {"use_pty": False, "combine_stderr": False},
            {"use_pty": False, "command": '/bin/bash -l -c "echo hello"'},
        ],
    ]
    for given_kwargs, expected_kwargs in cases:
        with patch("threadbare.operations._execute") as mockobj:
            mockobj.return_value = {
                "return_code": lambda: 0,
                "stdout": [],
                "stderr": [],
            }
            operations.remote(**merge(base, given_kwargs))
            mockobj.assert_called_with(**merge(base, expected_kwargs))


def test_remote_command_exception():
    kwargs = {
        "host_string": HOST,
        "port": PORT,
        "user": USER,
        "key_filename": PEM,
        "command": "echo hello",
    }
    m = mock.MagicMock()
    m.run_command = mock.Mock(side_effect=ValueError("earthshatteringkaboom"))
    with patch("threadbare.operations.SSHClient", return_value=m):
        with pytest.raises(operations.NetworkError):
            operations.remote(**kwargs)


def test_remote_command_timeout_exception():
    kwargs = {
        "host_string": HOST,
        "port": PORT,
        "user": USER,
        "key_filename": PEM,
        "command": "echo hello",
    }
    m = mock.MagicMock()
    m.run_command = mock.Mock(side_effect=pssh_exceptions.Timeout("foobar"))
    with patch("threadbare.operations.SSHClient", return_value=m):
        with pytest.raises(operations.NetworkError) as err:
            operations.remote(**kwargs)
        err = err.value
        assert type(err.wrapped) == pssh_exceptions.Timeout
        assert str(err) == "Timed out trying to connect. foobar"


# local


def test_lcd():
    "changes the local working directory"
    cur_cwd = cwd()
    new_cwd = "/tmp"
    assert not cur_cwd.startswith(new_cwd)  # sanity check
    with operations.lcd(new_cwd):
        assert cwd() == new_cwd
    assert cwd() == cur_cwd


def test_local_shell_command():
    "commands are run within a shell successfully"
    command = 'echo "hello world"'
    expected = {
        "return_code": 0,
        "succeeded": True,
        "failed": False,
        "command": '/bin/bash -l -c "echo \\"hello world\\""',
        "stdout": [],
        "stderr": [],
    }
    actual = operations.local(command)
    assert expected == actual


def test_local_shell_command_capture():
    "when output is being captured, shell command output on stdout is available"
    command = 'echo "hello world"'
    expected = {
        "return_code": 0,
        "succeeded": True,
        "failed": False,
        "command": '/bin/bash -l -c "echo \\"hello world\\""',
        "stdout": ["hello world"],
        "stderr": [],
    }
    actual = operations.local(command, capture=True)
    assert expected == actual


def test_local_command():
    "non-shell commands must pass their command as a list of arguments"
    command = ["echo", "hello world"]
    expected = {
        "succeeded": True,
        "failed": False,
        "return_code": 0,
        "command": command,
        "stdout": [],
        "stderr": [],
    }
    actual = operations.local(command, use_shell=False)
    assert expected == actual


def test_local_command_capture():
    "when output is being captured, non-shell command output on stdout is available"
    command = ["echo", "hello world"]
    expected = {
        "succeeded": True,
        "failed": False,
        "return_code": 0,
        "command": command,
        "stdout": ["hello world"],
        "stderr": [],
    }
    actual = operations.local(command, capture=True, use_shell=False)
    assert expected == actual


def test_local_command_non_arg_list():
    "non-shell commands must pass their command as a list of arguments"
    with pytest.raises(ValueError):
        operations.local("echo foo", use_shell=False)


def test_local_command_stderr():
    "when output is being captured, stderr is combined with stdout by default"
    command = 'echo "standard out"; >&2 echo "standard error"'
    expected = {
        "succeeded": True,
        "failed": False,
        "return_code": 0,
        "command": '/bin/bash -l -c "echo \\"standard out\\"; >&2 echo \\"standard error\\""',
        "stdout": ["standard out", "standard error"],
        "stderr": [],
    }
    actual = operations.local(command, capture=True)  # default is to combine
    assert expected == actual


def test_local_command_split_stderr():
    "when output is being captured, output on stderr is also available when `combine_stderr` is False"
    command = 'echo "standard out"; >&2 echo "standard error"'
    expected = {
        "succeeded": True,
        "failed": False,
        "return_code": 0,
        "command": '/bin/bash -l -c "echo \\"standard out\\"; >&2 echo \\"standard error\\""',
        "stdout": ["standard out"],
        "stderr": ["standard error"],
    }
    actual = operations.local(command, combine_stderr=False, capture=True)
    assert expected == actual


def test_local_command_non_zero_exit():
    "`local` commands raise a generic `RuntimeError` if the command they execute exits with a non-zero result"
    with pytest.raises(RuntimeError) as err:
        operations.local("exit 1")
    exc = err.value

    expected_err_msg = "local() encountered an error (return code 1) while executing '/bin/bash -l -c \"exit 1\"'"
    assert expected_err_msg == str(exc)

    expected_err_payload = {
        "command": '/bin/bash -l -c "exit 1"',
        "failed": True,
        "return_code": 1,
        "stderr": [],
        "stdout": [],
        "succeeded": False,
    }
    assert expected_err_payload == exc.result


def test_local_command_non_zero_custom_exit():
    "`local` commands may raise a specific exception if the command they execute exits with a non-zero result"
    with pytest.raises(ValueError) as err:
        operations.local("exit 1", abort_exception=ValueError)
    exc = err.value

    expected_err_msg = "local() encountered an error (return code 1) while executing '/bin/bash -l -c \"exit 1\"'"
    assert expected_err_msg == str(exc)

    expected_err_payload = {
        "command": '/bin/bash -l -c "exit 1"',
        "failed": True,
        "return_code": 1,
        "stderr": [],
        "stdout": [],
        "succeeded": False,
    }
    assert expected_err_payload == exc.result


def test_local_command_non_zero_exit_swallowed():
    "`local` commands that exit with a non-zero result do not raise an exception if `warn_only` is `True`"
    expected_result = {
        "command": '/bin/bash -l -c "exit 1"',
        "failed": True,
        "return_code": 1,
        "stderr": [],
        "stdout": [],
        "succeeded": False,
    }
    command = "exit 1"

    with state.settings(warn_only=True):
        result = operations.local(command)
        assert expected_result == result

    # ... and again, but as a parameter
    result = operations.local(command, warn_only=True)
    assert expected_result == result


def test_local_command_timeout():
    "`local` commands can be killed if their execution exceeds a timeout threshold"
    command = "sleep 5"
    expected = {
        "succeeded": False,
        "failed": True,
        "return_code": -9,  # SIGKILL
        "command": '/bin/bash -l -c "sleep 5"',
        "stdout": [],
        "stderr": [],
    }
    actual = operations.local(command, capture=True, timeout=0.1, warn_only=True)
    assert expected == actual


def test_single_command():
    "joins multiple commands into a single command to be run"
    cases = [
        [None, None],
        [[], None],
        [["foo"], "foo"],
        [["foo", "bar"], "foo && bar"],
        [["foo", "bar", "baz"], "foo && bar && baz"],
        [[1, 2, 3], "1 && 2 && 3"],
    ]
    for given, expected in cases:
        actual = operations.single_command(given)
        assert expected == actual, "failed case. %r != %r" % (expected, actual)


def test_local_quiet_param():
    "when quiet=True, nothing is sent to stdout or stderr"
    cmd = lambda: operations.local(
        'echo "hi!"; >&2 echo "hello!"', capture=False, combine_stderr=False
    )
    result = cmd()

    # with `local` it's either captured or printed.
    # if the results are empty it's because it was printed.
    # but how do we test? sys.stdout/sys.stderr are bypassed ... this test needs improving somehow.
    assert result["stdout"] == []
    assert result["stderr"] == []

    with operations.hide():
        result = cmd()
        assert result["stdout"] == []
        assert result["stderr"] == []


def test_prompt_operation_aborted():
    "calling `prompt` for user input with `abort_on_prompts=True` set raises an exception"
    with state.settings(abort_on_prompts=True):
        with pytest.raises(PromptedException):
            operations.prompt("some message")


def test_prompt_operation_aborted_custom_exception():
    "calling `prompt` for user input with `abort_on_prompts=True` and `abort_exception` set raises a custom exception"
    with state.settings(abort_on_prompts=True, abort_exception=ValueError):
        with pytest.raises(ValueError):
            operations.prompt("some message")


def test_formatted_output():
    "`_print_line`, called by `remote`, can have it's output string customised and still return the original string for processing"
    expected_stdout = "hello, world!"
    expected_buffer = "[35.153.232.132] stdout: hello, world!"

    line_template = "[{host}] {pipe}: {line}"
    strbuffer = StringIO()
    with state.settings(host_string="35.153.232.132", line_template=line_template):
        result = operations._print_line(strbuffer, "hello, world!")
        assert expected_stdout == result
        assert expected_buffer == strbuffer.getvalue()
