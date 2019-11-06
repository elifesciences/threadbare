from functools import partial
import threadbare
from threadbare import settings

def test_global_env():
    "`settings` context manager uses internal (empty) state dictionary if a specific dictionary isn't supplied"
    assert len(threadbare.ENV) == 0, "env is not initially empty"
    with settings(foo='bar'):
        assert len(threadbare.ENV) == 1, "env should contain one item"
        assert threadbare.ENV['foo'] == 'bar'
    assert len(threadbare.ENV) == 0, "env is not finally empty"

def test_env():
    "`settings` context manager will use the provided state dictionary if one is provided"
    env = {}
    assert len(env) == 0, "local env is not initially empty"
    assert len(threadbare.ENV) == 0, "global env is not initially empty"
    with settings(env, foo='bar'):
        assert len(env) == 1, "env should contain one item"
        assert len(threadbare.ENV) == 0, "global env should continue to be empty"
        assert env['foo'] == 'bar'
    assert len(env) == 0, "env is not finally empty"
    assert len(threadbare.ENV) == 0, "global env should continue to be empty"

def test_nested_state():
    env = {}
    with settings(env, foo='bar'):
        with settings(env, baz='bop'):
            assert env == {'foo': 'bar', 'baz': 'bop'}
    assert env == {}

def test_nested_state_initial_state():
    "state is returned to initial conditions"
    env = {'foo': 'bar'}
    with settings(env, baz='bop'):
        assert env == {'foo': 'bar', 'baz': 'bop'}
        with settings(env, boo='blah'):
            assert env == {'foo': 'bar', 'baz': 'bop', 'boo': 'blah'}
        assert env == {'foo': 'bar', 'baz': 'bop'}
    assert env == {'foo': 'bar'}

def test_uncontrolled_state_modification():
    "modifications to the state that happen outside of the context manager's control are preserved"
    env = {'foo': {'bar': 'baz'}}
    with settings(env):
        env['foo']['bar'] = 'bop'
    assert env == {'foo': {'bar': 'bop'}}

def test_settings_closure():
    enclosed = partial(settings, {})
    with enclosed(foo='bar') as env:
        assert env == {'foo': 'bar'}
        with enclosed(baz='bop') as env2:
            assert env2 == {'foo': 'bar', 'baz': 'bop'}
            assert env == {'foo': 'bar', 'baz': 'bop'}
        assert env == {'foo': 'bar'}
