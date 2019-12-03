import pytest
import time
from threadbare import execute
from threadbare.state import settings


def test_parallel_wrapper():
    "`parallel` correctly sets attributes on the function to be run in parallel with `execute`"

    def fn():
        pass

    assert not hasattr(fn, "parallel")
    assert not hasattr(fn, "pool_size")
    wrapped_func = execute.parallel(fn)
    assert hasattr(wrapped_func, "parallel")
    assert wrapped_func.parallel
    assert hasattr(wrapped_func, "pool_size")


def test_execute_serial():
    "`execute` will call a regular function and return a list of results"
    env = None

    def fn():
        return "hello, world"

    expected = ["hello, world"]
    assert expected == execute.execute(env, fn)


def test_execute_many_serial():
    "`serial` will wrap a given function and run it `pool_size` times, one after the other. complements `parallel`"
    env = None
    pool_size = 3
    wrapped_fn = execute.serial(lambda: "foo", pool_size)
    expected = ["foo", "foo", "foo"]
    assert expected == execute.execute(env, wrapped_fn)


def test_execute_many_serial_with_params():
    "`serial` will wrap a given function and run it `pool_size` times, but is ignored when `execute` is given a list of values"
    env = None

    def fn():
        with settings() as local_env:
            return "foo" + local_env["mykey"]

    wrapped_fn = execute.serial(fn, pool_size=1)
    param_key = "mykey"
    param_values = ["bar", "baz", "bop"]

    expected = ["foobar", "foobaz", "foobop"]
    assert expected == execute.execute(env, wrapped_fn, param_key, param_values)


def test_execute_with_missing():
    "both `param_key` and `param_values` should be provided or neither"

    def fn():
        return

    env = None
    with pytest.raises(ValueError):
        execute.execute(env, fn, param_key="good_key", param_values=None)

    with pytest.raises(ValueError):
        execute.execute(env, fn, param_values=["good", "values"])


def test_execute_with_bad_param_key():
    "`param_key` values must be strings"

    def fn():
        return

    env = None
    cases = [None, [], {}, (), 1, lambda x: x]
    for bad_param_key in cases:
        with pytest.raises(ValueError):
            execute.execute(env, fn, param_key=bad_param_key, param_values=["foo"])


def test_execute_with_bad_param_values():
    "`param_values` must be a list, tuple or set of values"

    def fn():
        return

    env = None
    cases = [None, 1, "", {}, lambda x: x]
    for bad_param_values in cases:
        with pytest.raises(ValueError):
            execute.execute(env, fn, param_key="mykey", param_values=bad_param_values)


def test_execute_many_parallel():
    "`parallel` will wrap a given function and run it `pool_size` times in parallel. complements `serial`"
    env = None
    pool_size = 3
    parallel_fn = execute.parallel(lambda: "foo", pool_size)
    expected = ["foo", "foo", "foo"]
    assert expected == execute.execute(env, parallel_fn)


def test_execute_many_parallel_with_params():
    "`parallel` will wrap a given function and run it `pool_size` times in parallel, but is ignored when `execute` is given a list of values"

    def fn():
        with settings() as local_env:
            return local_env

    parallel_fn = execute.parallel(fn, pool_size=1)
    param_key = "mykey"
    param_values = [1, 2, 3]

    expected = [
        {"parallel": True, "parent": "environment", "mykey": 1},
        {"parallel": True, "parent": "environment", "mykey": 2},
        {"parallel": True, "parent": "environment", "mykey": 3},
    ]

    with settings(parent="environment") as env:
        assert expected == execute.execute(env, parallel_fn, param_key, param_values)


def test_execute_many_parallel_raw_results():
    "calling `_parallel_execution` directly provides access to the state of the processes"

    def fn():
        with settings() as env:
            return env

    env = {"parent": "environment"}
    parallel_fn = execute.parallel(fn)
    param_key = "mykey"
    param_values = [1, 2, 3]
    expected = [
        {
            "name": "process--1",
            "exitcode": 0,
            "alive": False,
            "killed": False,
            "kill-signal": None,
            "result": {"parallel": True, "parent": "environment", "mykey": 1},
        },
        {
            "name": "process--2",
            "exitcode": 0,
            "alive": False,
            "killed": False,
            "kill-signal": None,
            "result": {"parallel": True, "parent": "environment", "mykey": 2},
        },
        {
            "name": "process--3",
            "exitcode": 0,
            "alive": False,
            "killed": False,
            "kill-signal": None,
            "result": {"parallel": True, "parent": "environment", "mykey": 3},
        },
    ]
    result_list = execute._parallel_execution(env, parallel_fn, param_key, param_values)

    # process pid is available but is not compared during testing. it's non-deterministic
    [result.pop("pid") for result in result_list]

    assert expected == result_list


def test_parallel_terminate():
    "when a process is terminated, ensure internal state is what we expect it to be"

    def fn():
        time.sleep(10)  # 'hang'
        return

    env = {}  # doesn't matter
    parallel_fn = execute.parallel(fn)
    param_key = param_values = None
    return_process_pool = True
    results_q, pool = execute._parallel_execution(
        env, parallel_fn, param_key, param_values, return_process_pool
    )

    process = pool[0]
    process.terminate()
    process.join()

    expected = {
        "alive": False,
        "exitcode": -15,  # negative SIGTERM
        "kill-signal": 15,  # SIGTERM
        "killed": True,
        "name": "process--1",
        #'pid': ... # not compared
    }
    actual_result = execute.process_status(process)
    del actual_result["pid"]

    assert expected == actual_result
    assert results_q.empty()
