import pytest
import time
from functools import partial
import threadbare
from threadbare import settings

# 'local' state
# this *is not* what Fabric does

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
    "settings decorator can be nested"
    env = {}
    with settings(env, foo='bar'):
        with settings(env, baz='bop'):
            assert env == {'foo': 'bar', 'baz': 'bop'}
    assert env == {}

def test_overridden_state():
    "overrides exist only for the scope of the context manager"
    env = {'foo': 'bar'}
    with settings(env, foo='baz'):
        assert env == {'foo': 'baz'}
    assert env == {'foo': 'bar'}

def test_deleted_state():
    "state is restored when a value is deleted"
    env = {'foo': 'bar'}
    with settings(env):
        del env['foo']
        assert env == {}
    assert env == {'foo': 'bar'}

def test_deleted_state_2():
    "state is restored when a value is removed"
    env = {'foo': 'bar'}
    with settings(env):
        env.pop('foo')
        assert env == {}
    assert env == {'foo': 'bar'}

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
    "modifications to the state that happen outside of the context manager's control (with ... as ...) are reverted on exit"
    env = {'foo': {'bar': 'baz'}}
    with settings(env):
        env['foo']['bar'] = 'bop'
        assert env == {'foo': {'bar': 'bop'}}
    assert env == {'foo': {'bar': 'baz'}}

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
    assert env == env2 == {}

# global state
# not pretty, often hard to reason about and may lead to weird behaviour if you're not careful.
# this is what Fabric does.

def test_global_env():
    "`settings` context manager uses global (and empty) state dictionary if a specific dictionary isn't supplied"
    assert threadbare.ENV == {}
    with settings(foo='bar'):
        assert threadbare.ENV == {'foo': 'bar'}
    assert threadbare.ENV == {}

def test_global_nested_state():
    "context managers can be nested for global state"
    assert threadbare.ENV == {}
    with settings(foo='bar'):
        with settings(baz='bop'):
            assert threadbare.ENV == {'foo': 'bar', 'baz': 'bop'}
    assert threadbare.ENV == {}

def test_global_overridden_state():
    "global overrides exist only for the scope of the context manager"
    assert threadbare.ENV == {}
    with settings(foo='baz') as local_env:
        assert local_env == {'foo': 'baz'}
    # python vagary that this can still be referenced
    # it should still be as we expect though.
    assert local_env == {} 
    assert threadbare.ENV == {}

def test_global_deleted_state():
    "original global state is restored if a value is deleted"
    assert threadbare.ENV == {}
    with settings(foo='bar', bar='baz') as env:
        assert threadbare.ENV == env == {'foo': 'bar', 'bar': 'baz'}
        del env['foo']
        assert threadbare.ENV == env == {'bar': 'baz'}
    assert threadbare.ENV == env == {}

def test_uncontrolled_global_state_modification():
    """modifications to global state that happen outside of the context manager's 
    control (with ... as ...) are available as expected BUT are reverted on exit"""
    assert threadbare.ENV == {}
    with settings() as env:
        threadbare.ENV['foo'] = {'bar': 'bop'}
        assert env == {'foo': {'bar': 'bop'}}
    assert threadbare.ENV == env == {}    

# 

def test_parallel_wrapper():
    "`parallel` correctly sets attributes on the function to be run in parallel with `execute`"
    def fn():
        pass
    assert not hasattr(fn, 'parallel')
    assert not hasattr(fn, 'pool_size')
    wrapped_func = threadbare.parallel(fn)
    assert hasattr(wrapped_func, 'parallel')
    assert wrapped_func.parallel
    assert hasattr(wrapped_func, 'pool_size')

def test_execute_serial():
    "`execute` will call a regular function and return a list of results"
    env = None
    def fn():
        return "hello, world"
    expected = ["hello, world"]
    assert expected == threadbare.execute(env, fn)

def test_execute_many_serial():
    "`serial` will wrap a given function and run it `pool_size` times, one after the other. complements `parallel`"
    env = None
    pool_size=3
    wrapped_fn = threadbare.serial(lambda: "foo", pool_size)
    expected = ["foo", "foo", "foo"]
    assert expected == threadbare.execute(env, wrapped_fn)

def test_execute_many_serial_with_params():
    "`serial` will wrap a given function and run it `pool_size` times, but is ignored when `execute` is given a list of values"
    env = None
    def fn():
        with settings() as local_env:
            return "foo" + local_env['mykey']
    wrapped_fn = threadbare.serial(fn, pool_size=1)
    param_key = "mykey"
    param_values =["bar", "baz", "bop"]
    
    expected = ["foobar", "foobaz", "foobop"]
    assert expected == threadbare.execute(env, wrapped_fn, param_key, param_values)

def test_execute_with_missing():
    "both `param_key` and `param_values` should be provided or neither"
    def fn():
        return
    env = None
    with pytest.raises(ValueError):
        threadbare.execute(env, fn, param_key='good_key', param_values=None)

    with pytest.raises(ValueError):
        threadbare.execute(env, fn, param_values=['good', 'values'])

def test_execute_with_bad_param_key():
    "`param_key` values must be strings"
    def fn():
        return
    env = None
    cases = [None, [], {}, (), 1, lambda x: x]
    for bad_param_key in cases:
        with pytest.raises(ValueError):
            threadbare.execute(env, fn, param_key=bad_param_key, param_values=["foo"])

def test_execute_with_bad_param_values():
    "`param_values` must be a list, tuple or set of values"
    def fn():
        return
    env = None
    cases = [None, 1, "", {}, lambda x: x]
    for bad_param_values in cases:
        with pytest.raises(ValueError):
            threadbare.execute(env, fn, param_key='mykey', param_values=bad_param_values)

def test_execute_many_parallel():
    "`parallel` will wrap a given function and run it `pool_size` times in parallel. complements `serial`"
    env = None
    pool_size = 3
    parallel_fn = threadbare.parallel(lambda: "foo", pool_size)
    expected = ["foo", "foo", "foo"]
    assert expected == threadbare.execute(env, parallel_fn)

def test_execute_many_parallel_with_params():
    "`parallel` will wrap a given function and run it `pool_size` times in parallel, but is ignored when `execute` is given a list of values"
    def fn():
        with settings() as local_env:
            return local_env
    parallel_fn = threadbare.parallel(fn, pool_size=1)
    param_key = 'mykey'
    param_values = [1,2,3]
    
    expected = [{'parent': 'environment', "mykey": 1},
                {'parent': 'environment', "mykey": 2},
                {'parent': 'environment', "mykey": 3}]

    with settings(parent='environment') as env:
        assert expected == threadbare.execute(env, parallel_fn, param_key, param_values)

def test_execute_many_parallel_raw_results():
    "calling `_parallel_execution` directly provides access to the state of the processes"
    def fn():
        with settings() as env:
            return env
    env = {'parent': 'environment'}
    parallel_fn = threadbare.parallel(fn)
    param_key = 'mykey'
    param_values = [1, 2, 3]
    expected = [
        {'name': 'process--1', 'exitcode': 0, 'alive': False, 'killed': False, 'kill-signal': None, 'result': {'parent': 'environment', 'mykey': 1}},
        {'name': 'process--2', 'exitcode': 0, 'alive': False, 'killed': False, 'kill-signal': None, 'result': {'parent': 'environment', 'mykey': 2}},
        {'name': 'process--3', 'exitcode': 0, 'alive': False, 'killed': False, 'kill-signal': None, 'result': {'parent': 'environment', 'mykey': 3}}]
    result_list = threadbare._parallel_execution(env, parallel_fn, param_key, param_values)

    # process pid is available but is not compared during testing. it's non-deterministic
    [result.pop('pid') for result in result_list]

    assert expected == result_list

def test_parallel_terminate():
    "when a process is terminated, ensure internal state is what we expect it to be"
    def fn():
        time.sleep(10) # 'hang'
        return

    env = {} # doesn't matter
    parallel_fn = threadbare.parallel(fn)
    param_key = param_values = None
    return_process_pool=True
    results_q, pool = threadbare._parallel_execution(env, parallel_fn, param_key, param_values, return_process_pool)
    
    process = pool[0]
    process.terminate()
    process.join()

    expected = {
        'alive': False,
        'exitcode': -15, # negative SIGTERM
        'kill-signal': 15, # SIGTERM
        'killed': True,
        'name': 'process--1',
        #'pid': ... # not compared
    }
    actual_result = threadbare.process_status(process)
    del actual_result['pid']

    assert expected == actual_result
    assert results_q.empty()
