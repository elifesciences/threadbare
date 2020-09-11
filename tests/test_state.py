import pytest
from threadbare import state
from threadbare.state import settings
import copy

# lsh@2019-12: careful manipulation of global state is how Fabric does most of it's magic.
# it's not pretty, often hard to reason about and may lead to weird behaviour if you're not careful.

# every test gets a @reset
# if a test fails for whatever reason, it may leave the other tests in an unknown state
# inverse is also true. a subsequent test may end up relying on the successful modification in previous test
def reset(fn):
    def wrapper():
        try:
            result = fn()
            return result
        finally:
            state.ENV = state.initial_state()

    return wrapper


@reset
def test_global_env():
    "`settings` context manager uses global (and empty) state dictionary if a specific dictionary isn't supplied"
    assert state.ENV == {}
    with settings(foo="bar"):
        assert state.ENV == {"foo": "bar"}
    assert state.ENV == {}


@reset
def test_global_nested_state():
    "context managers can be nested for global state"
    assert state.ENV == {}
    with settings(foo="bar"):
        with settings(baz="bop"):
            assert state.ENV == {"foo": "bar", "baz": "bop"}
    assert state.ENV == {}


@reset
def test_global_overridden_state():
    "global overrides exist only for the scope of the context manager"
    assert state.ENV == {}
    with settings(foo="baz") as local_env:
        assert local_env == {"foo": "baz"}
    # python vagary that this can still be referenced
    # it should still be as we expect though.
    assert local_env == {}
    assert state.ENV == {}


@reset
def test_global_deleted_state():
    "original global state is restored if a value is deleted"
    assert state.ENV == {}
    with settings(foo="bar", bar="baz") as env:
        assert state.ENV == env == {"foo": "bar", "bar": "baz"}
        del env["foo"]
        assert state.ENV == env == {"bar": "baz"}
    assert state.ENV == env == {}


@reset
def test_uncontrolled_global_state_modification():
    "modifications to global state outside of a context manager are prohibited"
    assert isinstance(state.ENV, state.FreezeableDict)  # type check
    assert state.ENV == {}  # empty value
    with pytest.raises(ValueError):
        state.ENV["foo"] = "bar"


@reset
def test_uncontrolled_global_state_modification_2():
    """modifications to global state that happen outside of the context manager's
    control (with ... as ...) are available as expected BUT are reverted on exit"""
    assert isinstance(state.ENV, state.FreezeableDict)
    assert state.ENV == {}
    with settings() as env:
        state.ENV["foo"] = {"bar": "bop"}
        assert env == {"foo": {"bar": "bop"}}
    assert state.ENV == env == {}


@reset
def test_uncontrolled_global_state_modification_3():
    "modifications to global state outside of a context manager are prohibited UNLESS you're using own dictionary-like state object"
    assert isinstance(state.ENV, state.FreezeableDict)
    assert state.ENV == {}

    state.ENV = {}
    assert not isinstance(state.ENV, state.FreezeableDict)

    # ENV is now a regular dictionary

    state.ENV["foo"] = "bar"
    assert state.ENV["foo"] == "bar"


@reset
def test_global_state_is_unlocked_inside_context():
    "`state.ENV` is only writeable within the context manager"
    assert isinstance(state.ENV, state.FreezeableDict)
    assert state.ENV.read_only
    with settings():
        assert not state.ENV.read_only
        state.ENV["foo"] = "bar"
    assert state.ENV.read_only
    assert state.ENV == {}


@reset
def test_nested_global_state_is_unlocked_inside_context():
    "`state.ENV` is only writeable within the context manager, including nested context managers"
    assert isinstance(state.ENV, state.FreezeableDict)
    assert state.ENV.read_only
    with settings():
        assert not state.ENV.read_only
        state.ENV["foo"] = "bar"

        with settings():
            assert not state.ENV.read_only

        assert not state.ENV.read_only

    assert state.ENV.read_only
    assert state.ENV == {}


@reset
def test_lockable_dict():
    "a lockable dictionary has a simple locked/unlocked boolean preventing write access. default is unlocked"
    foo = state.FreezeableDict()
    assert not foo.read_only

    state.read_only(foo)
    assert foo.read_only

    state.read_write(foo)
    assert not foo.read_only


@reset
def test_lockable_dict_attrs_preserved():
    "creating a copy of a FreezeableDict objects preserves the state of the locked/unlocked boolean"
    foo = state.FreezeableDict()
    assert not foo.read_only

    state.read_only(foo)  # alter foo
    assert foo.read_only

    baz = copy.deepcopy(foo)  # happens when we context shift
    assert baz.read_only
    assert isinstance(baz, state.FreezeableDict)


# cleanup


@reset
def test_cleanup():
    "'cleanup' functions can be added that will be executed when the context manager is left"
    side_effects = {}

    def cleanup_fn():
        side_effects["?"] = "!"

    with settings():
        state.add_cleanup(cleanup_fn)
    assert side_effects["?"] == "!"


@reset
def test_nested_scopes_dont_cleanup_parent_scopes():
    "cleanup functions are only called for the scope they were added to"
    side_effects = {}

    def cleanup_fn_1():
        side_effects["1"] = "scope 1 cleaned up"

    def cleanup_fn_2():
        side_effects["2"] = "scope 2 cleaned up"

    with settings():
        state.add_cleanup(cleanup_fn_1)
        with settings():
            state.add_cleanup(cleanup_fn_2)
        assert side_effects == {"2": "scope 2 cleaned up"}
    assert side_effects == {"2": "scope 2 cleaned up", "1": "scope 1 cleaned up"}


@reset
def test_set_defaults():
    "global state defaults can be easily set"
    expected_initial_state = state.initial_state()
    assert state.ENV == expected_initial_state
    assert state.ENV.read_only

    state.set_defaults({"foo": "bar"})
    assert state.DEPTH == 0

    expected_state = state.FreezeableDict({"foo": "bar"})
    assert state.ENV == expected_state
    assert isinstance(state.ENV, state.FreezeableDict)
    assert state.ENV.read_only


@reset
def test_set_defaults_settings():
    "global state defaults can be easily set"
    state.set_defaults({"foo": "bar"})
    with state.settings(foo="baz"):
        assert state.ENV == {"foo": "baz"}
    assert state.ENV == {"foo": "bar"}
    assert state.DEPTH == 0
