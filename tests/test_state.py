import pytest
from functools import partial
from threadbare import state
from threadbare.state import settings
import copy

# 'local' state
# this *is not* what Fabric does

def test_env():
    "`settings` context manager will use the provided state dictionary if one is provided"
    env = {}
    assert len(env) == 0, "local env is not initially empty"
    assert len(state.ENV) == 0, "global env is not initially empty"
    with settings(env, foo='bar'):
        assert len(env) == 1, "env should contain one item"
        assert len(state.ENV) == 0, "global env should continue to be empty"
        assert env['foo'] == 'bar'
    assert len(env) == 0, "env is not finally empty"
    assert len(state.ENV) == 0, "global env should continue to be empty"

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

# every test gets a @reset
# if a test fails for whatever reason, it may leave the other tests in an unknown state
# inverse is also true. a subsequent test may end up relying on the successful modification in previous test
def reset(fn):
    def wrapper():
        result = fn()
        state.ENV = state.LockableDict()
        state.read_only(state.ENV)
        return result
    return wrapper

@reset
def test_global_env():
    "`settings` context manager uses global (and empty) state dictionary if a specific dictionary isn't supplied"
    assert state.ENV == {}
    with settings(foo='bar'):
        assert state.ENV == {'foo': 'bar'}
    assert state.ENV == {}

@reset
def test_global_nested_state():
    "context managers can be nested for global state"
    assert state.ENV == {}
    with settings(foo='bar'):
        with settings(baz='bop'):
            assert state.ENV == {'foo': 'bar', 'baz': 'bop'}
    assert state.ENV == {}

@reset
def test_global_overridden_state():
    "global overrides exist only for the scope of the context manager"
    assert state.ENV == {}
    with settings(foo='baz') as local_env:
        assert local_env == {'foo': 'baz'}
    # python vagary that this can still be referenced
    # it should still be as we expect though.
    assert local_env == {} 
    assert state.ENV == {}

@reset
def test_global_deleted_state():
    "original global state is restored if a value is deleted"
    assert state.ENV == {}
    with settings(foo='bar', bar='baz') as env:
        assert state.ENV == env == {'foo': 'bar', 'bar': 'baz'}
        del env['foo']
        assert state.ENV == env == {'bar': 'baz'}
    assert state.ENV == env == {}

@reset
def test_uncontrolled_global_state_modification():
    "modifications to global state outside of a context manager are prohibited"
    assert isinstance(state.ENV, state.LockableDict) # type check
    assert state.ENV == {} # empty value
    with pytest.raises(ValueError):
        state.ENV['foo'] = 'bar'

@reset
def test_uncontrolled_global_state_modification_2():
    """modifications to global state that happen outside of the context manager's 
    control (with ... as ...) are available as expected BUT are reverted on exit"""
    assert isinstance(state.ENV, state.LockableDict)
    assert state.ENV == {}
    with settings() as env:
        state.ENV['foo'] = {'bar': 'bop'}
        assert env == {'foo': {'bar': 'bop'}}
    assert state.ENV == env == {}

@reset
def test_uncontrolled_global_state_modification_3():
    "modifications to global state outside of a context manager are prohibited UNLESS you're using own dictionary-like state object"
    assert isinstance(state.ENV, state.LockableDict)
    assert state.ENV == {}

    state.ENV = {}
    assert not isinstance(state.ENV, state.LockableDict)

    # ENV is now a regular dictionary
    
    state.ENV['foo'] = 'bar'
    assert state.ENV['foo'] == 'bar'

@reset
def test_global_state_is_unlocked_inside_context():
    assert isinstance(state.ENV, state.LockableDict)
    assert state.ENV.read_only
    with settings():
        assert not state.ENV.read_only
        state.ENV['foo'] = 'bar'
    assert state.ENV.read_only
    assert state.ENV == {}

@reset
def test_nested_global_state_is_unlocked_inside_context():
    assert isinstance(state.ENV, state.LockableDict)
    assert state.ENV.read_only
    with settings():
        assert not state.ENV.read_only
        state.ENV['foo'] = 'bar'
        
        with settings():
            assert not state.ENV.read_only

        assert not state.ENV.read_only
            
    assert state.ENV.read_only
    assert state.ENV == {}

# cleanup

@reset
def test_cleanup():
    side_effect = {}
    def cleanup_fn():
        side_effect['?'] = "!"
    with settings():
        state.add_cleanup(cleanup_fn)
    assert side_effect['?'] == "!"

def test_nested_scopes_dont_cleanup_parent_scopes():
    "cleanup functions are only called for the scope they were added to"
    side_effects = {}
    def cleanup_fn_1():
        side_effects['1'] = "scope 1 cleaned up"
    def cleanup_fn_2():
        side_effects['2'] = "scope 2 cleaned up"
    with settings():
        state.add_cleanup(cleanup_fn_1)
        with settings():
            state.add_cleanup(cleanup_fn_2)
        assert side_effects == {'2': 'scope 2 cleaned up'}
    assert side_effects == {'2': 'scope 2 cleaned up', '1': 'scope 1 cleaned up'}

#

@reset
def test_lockable_dict():
    foo = state.LockableDict()
    assert not foo.read_only # default is unlocked
    
    state.read_only(foo)
    assert foo.read_only
    
    state.read_write(foo)
    assert not foo.read_only

@reset
def test_lockable_dict_attrs_preserved():
    foo = state.LockableDict()
    assert not foo.read_only # default is unlocked
    
    state.read_only(foo) # alter foo
    assert foo.read_only

    baz = copy.deepcopy(foo) # happens when we context shift
    assert baz.read_only
    assert isinstance(baz, state.LockableDict)
