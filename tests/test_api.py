import unittest.mock
from unittest.mock import patch
from threadbare import api, merge

# simple remote calls

HOST = 'testhost'
USER = 'testuser'
PORT = 666
PEM = "/home/testuser/.ssh/id_rsa"

def test_remote_args_to_execute():
    "`api.remote` calls `api._execute` with the correct arguments"
    with patch('threadbare.api._execute') as mockobj:
        api.remote('echo hello', host=HOST, port=PORT, user=USER, private_key_file=PEM)

    expected_kwargs = {
        'host': HOST,
        'port': PORT,
        'user': USER,
        'private_key_file': PEM,
        
        'use_pty': True,
        'command': '/bin/bash -l -c "echo hello"'
    }
    mockobj.assert_called_with(**expected_kwargs)

def test_remote_sudo_args_to_execute():
    "`api.remote_sudo` calls `api._execute` with the correct arguments"
    with patch('threadbare.api._execute') as mockobj:
        api.remote_sudo('echo hello', host=HOST, port=PORT, user=USER, private_key_file=PEM)

    expected_kwargs = {
        'host': HOST,
        'port': PORT,
        'user': USER,
        'private_key_file': PEM,

        'use_pty': True,
        'command': 'sudo --non-interactive /bin/bash -l -c "echo hello"'
    }
    mockobj.assert_called_with(**expected_kwargs)

# remote calls with non-default args

def test_remote_non_default_args():
    "`api.remote_sudo` calls `api._execute` with the correct arguments"
    base = {
        'host': HOST,
        'port': PORT,
        'user': USER,
        'private_key_file': PEM,
    }
    cases = [
        # non-shell regular command
        [{'use_shell': False}, {'use_pty': True, 'command': 'echo hello'}],

        # non-shell, non-tty command
        [{'use_shell': False, 'combine_stderr': False}, {'use_pty': False, 'command': 'echo hello'}],

        # non-shell sudo command
        [{'use_shell': False, 'use_sudo': True}, {'use_pty': True, 'command': 'sudo --non-interactive echo hello'}]
    ]
    for given_kwargs, expected_kwargs in cases:
        with patch('threadbare.api._execute') as mockobj:
            api.remote('echo hello', **merge(base, given_kwargs))
        mockobj.assert_called_with(**merge(base, expected_kwargs))
    
