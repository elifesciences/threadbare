import pytest

try:
    import unittest.mock as mock
    from unittest.mock import patch
except ImportError:
    import mock
    from mock import patch

from threadbare import operations, state
from threadbare.common import merge, cwd
from pssh import exceptions as pssh_exceptions

# remote

HOST = "testhost"
USER = "testuser"
PORT = 666
PEM = "/home/testuser/.ssh/id_rsa"

def test_hide():
    "`hide` in threadbare just sets quiet=True. It's much more fine grained in fabric."
    with operations.hide():
        assert state.ENV == {'quiet': True}

def test_hide_w_args():
    "`hide` in threadbare supports arguments for the types of things to be hidden, all of which are ignored"
    with operations.hide('egg'):
        assert state.ENV == {'quiet': True}

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
        "command": '/bin/bash -l -c "cd \\"/tmp\\" && pwd"',
    }
    mockobj.assert_called_with(**expected_kwargs)


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
        # edge cases
        # shell, non-tty command
        # this may be a parallel-ssh bug. in order to combine output streams, `pty` must be off
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
