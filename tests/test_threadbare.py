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
    "access to an enclosed state dictionary without reference to the original is still possible"
    enclosed = partial(settings, {})
    with enclosed(foo='bar') as env:
        assert env == {'foo': 'bar'}
        with enclosed(baz='bop') as env2:
            assert env2 == {'foo': 'bar', 'baz': 'bop'}
            assert env == {'foo': 'bar', 'baz': 'bop'}
        assert env == {'foo': 'bar'}

def test_settings_nested_closure():
    "state dictionary reference provided in nested scopes is preserved"
    env = {}
    enclosed = partial(settings, env)
    with enclosed(foo='bar'):
        with enclosed(baz='bop') as env2:
            assert env == env2 == {'foo':'bar','baz':'bop'}
    assert env == {}

# 

def test_parallel_wrapper():
    env = {}
    def fn():
        pass
    wrapped_func = threadbare.parallel(env, fn)
    assert hasattr(wrapped_func, 'parallel')
    assert wrapped_func.parallel
    assert hasattr(wrapped_func, 'pool_size')

def test_execute():
    env = {}
    def fn():
        return "hello, world"
    expected = ["hello, world"]
    assert expected == threadbare.execute(env, fn)

def test_execute_many_serial():
    env = {}
    def fn():
        return "foo"
    expected = ["foo"]
    assert expected == threadbare.execute(env, fn)

def test_execute_many_serial_params():
    def fn():
        with settings() as env:
            return "foo" + str(env['key'])
    expected = ["foobar", "foobaz", "foobop"]
    local_env = None # emulates Fabric's global `_env` dictionary, but less than ideal
    assert expected == threadbare.execute(local_env, fn, param_key="key", param_values=["bar", "baz", "bop"])

def test_execute_many_parallel():
    env = {}
    def fn():
        return "foo"
    pool_size = 3
    parallel_fn = threadbare.parallel(env, fn, pool_size=pool_size)
    expected = ["foo"] * pool_size
    assert expected == threadbare.execute(env, parallel_fn)
