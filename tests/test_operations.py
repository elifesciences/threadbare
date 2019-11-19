import pytest
import unittest.mock as mock
from unittest.mock import patch
from threadbare import operations
from threadbare.common import merge
from pssh import exceptions as pssh_exceptions

# simple remote calls

HOST = 'testhost'
USER = 'testuser'
PORT = 666
PEM = "/home/testuser/.ssh/id_rsa"

def test_remote_args_to_execute():
    "`operations.remote` calls `operations._execute` with the correct arguments"
    with patch('threadbare.operations._execute') as mockobj:
        operations.remote('echo hello', host=HOST, port=PORT, user=USER, key_filename=PEM)

    expected_kwargs = {
        'host': HOST,
        'port': PORT,
        'user': USER,
        'key_filename': PEM,
        
        'use_pty': True,
        'command': '/bin/bash -l -c "echo hello"'
    }
    mockobj.assert_called_with(**expected_kwargs)

def test_remote_sudo_args_to_execute():
    "`operations.remote_sudo` calls `operations._execute` with the correct arguments"
    with patch('threadbare.operations._execute') as mockobj:
        operations.remote_sudo('echo hello', host=HOST, port=PORT, user=USER, key_filename=PEM)

    expected_kwargs = {
        'host': HOST,
        'port': PORT,
        'user': USER,
        'key_filename': PEM,

        'use_pty': True,
        'command': 'sudo --non-interactive /bin/bash -l -c "echo hello"'
    }
    mockobj.assert_called_with(**expected_kwargs)

# remote calls with non-default args

def test_remote_non_default_args():
    "`operations.remote` calls `operations._execute` with the correct arguments"
    base = {
        'host': HOST,
        'port': PORT,
        'user': USER,
        'key_filename': PEM,
        'command': 'echo hello',
    }
    
    # given args, expected args
    cases = [
        # non-shell regular command
        [{'use_shell': False}, {'use_pty': True, 'command': 'echo hello'}],

        # non-shell, non-tty command
        [{'use_shell': False, 'combine_stderr': False}, {'use_pty': False, 'command': 'echo hello'}],

        # non-shell sudo command
        [{'use_shell': False, 'use_sudo': True}, {'use_pty': True, 'command': 'sudo --non-interactive echo hello'}],

        # shell, regular command
        [{'use_shell': True},  {'use_pty': True, 'command': '/bin/bash -l -c "echo hello"'}],

        # shell, sudo command
        [{'use_shell': True, 'use_sudo': True},  {'use_pty': True, 'command': 'sudo --non-interactive /bin/bash -l -c "echo hello"'}],

        # shell escoperationsng
        [{'command': 'foo=bar; echo "bar? $foo!"'},  {'use_pty': True, 'command': '/bin/bash -l -c "foo=bar; echo \\"bar? \\$foo!\\""'}],

        # shell escoperationsng, non-shell
        [{'command': 'foo=bar; echo "bar? $foo!"', 'use_shell': False},  {'use_pty': True, 'command': 'foo=bar; echo "bar? $foo!"'}],
        
        # edge cases

        # shell, non-tty command
        # this may be a parallel-ssh bug. in order to combine output streams, `pty` must be off
        [{'use_pty': False},  {'use_pty': True, # !!
                               'command': '/bin/bash -l -c "echo hello"'}],

        # if you really need a `pty`, you'll have to handle separate stdout/stderr streams
        [{'use_pty': False, 'combine_stderr': False}, {'use_pty': False, 'command': '/bin/bash -l -c "echo hello"'}],
        
    ]
    for given_kwargs, expected_kwargs in cases:
        with patch('threadbare.operations._execute') as mockobj:
            operations.remote(**merge(base, given_kwargs))
        mockobj.assert_called_with(**merge(base, expected_kwargs))

def test_remote_command_exception():
    kwargs = {
        'host': HOST,
        'port': PORT,
        'user': USER,
        'key_filename': PEM,
        'command': 'echo hello',
    }
    m = mock.MagicMock()
    m.run_command = mock.Mock(side_effect=ValueError('earthshatteringkaboom'))
    with patch('threadbare.operations.SSHClient', return_value=m):
        with pytest.raises(operations.NetworkError):
            operations.remote(**kwargs)

def test_remote_command_timeout_exception():
    kwargs = {
        'host': HOST,
        'port': PORT,
        'user': USER,
        'key_filename': PEM,
        'command': 'echo hello',
    }
    m = mock.MagicMock()
    m.run_command = mock.Mock(side_effect=pssh_exceptions.Timeout('foobar'))
    with patch('threadbare.operations.SSHClient', return_value=m):
        with pytest.raises(operations.NetworkError) as err:
            operations.remote(**kwargs)
        err = err.value
        assert type(err.wrapped) == pssh_exceptions.Timeout
        assert str(err) == 'Timed out trying to connect. foobar'

