import pytest
import time
import logging
from unittest.mock import patch
from threadbare import execute, operations
from threadbare.state import settings
from threadbare.common import PromptedException


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

    def fn():
        return "hello, world"

    expected = ["hello, world"]
    assert expected == execute.execute(fn)


def test_execute_many_serial():
    "`serial` will wrap a given function and run it `pool_size` times, one after the other. complements `parallel`"
    pool_size = 3
    wrapped_fn = execute.serial(lambda: "foo", pool_size)
    expected = ["foo", "foo", "foo"]
    assert expected == execute.execute(wrapped_fn)


def test_execute_many_serial_with_params():
    "`serial` will wrap a given function and run it `pool_size` times, but is ignored when `execute` is given a list of values"

    def fn():
        with settings() as local_env:
            return "foo" + local_env["mykey"]

    wrapped_fn = execute.serial(fn, pool_size=1)
    param_key = "mykey"
    param_values = ["bar", "baz", "bop"]

    expected = ["foobar", "foobaz", "foobop"]
    assert expected == execute.execute(wrapped_fn, param_key, param_values)


def test_execute_with_missing():
    "both `param_key` and `param_values` should be provided or neither"

    def fn():
        return

    with pytest.raises(ValueError):
        execute.execute(fn, param_key="good_key", param_values=None)

    with pytest.raises(ValueError):
        execute.execute(fn, param_values=["good", "values"])


def test_execute_with_bad_param_key():
    "`param_key` values must be strings"

    def fn():
        return

    cases = [None, [], {}, (), 1, lambda x: x]
    for bad_param_key in cases:
        with pytest.raises(ValueError):
            execute.execute(fn, param_key=bad_param_key, param_values=["foo"])


def test_execute_with_bad_param_values():
    "`param_values` must be a list, tuple or set of values"

    def fn():
        return

    cases = [None, 1, "", {}, lambda x: x]
    for bad_param_values in cases:
        with pytest.raises(ValueError):
            execute.execute(fn, param_key="mykey", param_values=bad_param_values)


def test_execute_workerfn_exception():
    "exceptions thrown by worker functions while being executed serially are left uncaught"
    exc_msg = "omg. dead"

    def workerfn():
        raise EnvironmentError(exc_msg)

    # what should the behaviour here be? consistent with `parallel`?
    # in that case, the exception should be returned as a result.
    # I think builder expects exceptions to be thrown rather than returned however.
    with pytest.raises(EnvironmentError) as exc:
        execute.execute(workerfn)
        assert isinstance(exc, EnvironmentError)
        assert str(exc) == exc_msg


def test_execute_many_parallel():
    "`parallel` will wrap a given function and run it `pool_size` times in parallel. complements `serial`"
    pool_size = 3
    parallel_fn = execute.parallel(lambda: "foo", pool_size)
    expected = ["foo", "foo", "foo"]
    assert expected == execute.execute(parallel_fn)


def test_execute_many_parallel_with_params():
    "`parallel` will wrap a given function and run it `pool_size` times in parallel, but is ignored when `execute` is given a list of values"

    def fn():
        with settings() as local_env:
            return local_env

    parallel_fn = execute.parallel(fn, pool_size=1)
    param_key = "mykey"
    param_values = [1, 2, 3]

    expected = [
        {
            "parallel": True,
            "abort_on_prompts": True,
            "parent": "environment",
            "mykey": 1,
        },
        {
            "parallel": True,
            "abort_on_prompts": True,
            "parent": "environment",
            "mykey": 2,
        },
        {
            "parallel": True,
            "abort_on_prompts": True,
            "parent": "environment",
            "mykey": 3,
        },
    ]

    with settings(parent="environment"):
        assert expected == execute.execute(parallel_fn, param_key, param_values)


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
            "result": {
                "parallel": True,
                "abort_on_prompts": True,
                "parent": "environment",
                "mykey": 1,
            },
        },
        {
            "name": "process--2",
            "exitcode": 0,
            "alive": False,
            "killed": False,
            "kill-signal": None,
            "result": {
                "parallel": True,
                "abort_on_prompts": True,
                "parent": "environment",
                "mykey": 2,
            },
        },
        {
            "name": "process--3",
            "exitcode": 0,
            "alive": False,
            "killed": False,
            "kill-signal": None,
            "result": {
                "parallel": True,
                "abort_on_prompts": True,
                "parent": "environment",
                "mykey": 3,
            },
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


def test_parallel_worker_exceptions__raise_errors():
    "exceptions in worker functions are raised when encountered in the results"
    exc_msg = "omg. dead"

    @execute.parallel
    def workerfn():
        raise EnvironmentError(exc_msg)

    with pytest.raises(EnvironmentError) as e:
        execute.execute(workerfn)
        expected = exc_msg
        assert expected == str(e)


def test_parallel_worker_exceptions__swallow_errors():
    "exceptions in worker functions are returned as results when `raise_unhandled_errors` is `False`"
    exc_msg = "omg. dead"

    @execute.parallel
    def workerfn():
        raise EnvironmentError(exc_msg)

    results = execute.execute(workerfn, raise_unhandled_errors=False)
    unhandled_exception = results[0]
    assert isinstance(unhandled_exception, EnvironmentError)
    assert str(unhandled_exception) == exc_msg


def test_execute_with_hosts():
    "`execute_with_hosts` returns a dictionary of results keyed by host. like Fabric."

    def workerfn():
        with settings() as env:
            return env["host_string"] + "host"

    hosts = ["local", "good"]
    results = execute.execute_with_hosts(workerfn, hosts)
    expected = {"local": "localhost", "good": "goodhost"}
    assert expected == results


def test_parallel_with_prompts__raise_errors():
    "prompts issued while executing a worker function in parallel return the PromptedException"

    @execute.parallel
    def workerfn():
        return operations.prompt("gimmie")

    with pytest.raises(PromptedException) as e:
        execute.execute(workerfn)
        expected = "prompted with: gimmie"
        assert expected == str(e)


def test_parallel_with_prompts__swallow_errors():
    "prompts issued while executing a worker function in parallel return the PromptedException"

    @execute.parallel
    def workerfn():
        return operations.prompt("gimmie")

    results = execute.execute(workerfn, raise_unhandled_errors=False)
    expected = str(PromptedException("prompted with: gimmie"))
    assert expected == str(results[0])


def test_parallel_with_prompts_custom__raise_errors():
    "prompts issued while executing a worker function in parallel with `abort_exception` return a custom exception"

    @execute.parallel
    def workerfn():
        return operations.prompt("gimmie")

    with settings(abort_exception=ValueError):
        with pytest.raises(ValueError) as e:
            execute.execute(workerfn)
            expected = "prompted with: gimmie"
            assert expected == str(e)


def test_parallel_with_prompts_custom__swallow_errors():
    "prompts issued while executing a worker function in parallel with `abort_exception` set returns the custom exception"

    @execute.parallel
    def workerfn():
        return operations.prompt("gimmie")

    with settings(abort_exception=ValueError):
        results = execute.execute(workerfn, raise_unhandled_errors=False)
        expected = "prompted with: gimmie"
        assert expected == str(results[0])


def test_execute_with_prompts_override__raise_errors():
    """prompts issued while executing a worker function in parallel with `abort_on_prompts` set to `False` will get the unsupported `EOFError` raised.
    When `raise_unhandled_errors` is set to `True` (default) the `EOFError` will be re-thrown."""

    @execute.parallel
    def workerfn():
        with settings(abort_on_prompts=False):
            return operations.prompt("gimmie")

    with pytest.raises(EOFError) as e:
        execute.execute(workerfn)
        expected = "EOF when reading a line"
        assert expected == str(e)


def test_execute_with_prompts_override__swallow_errors():
    """prompts issued while executing a worker function in parallel with `abort_on_prompts` set to `False` will get the unsupported `EOFError` raised.
    When `raise_unhandled_errors` is set to `False` the `EOFError` is available in the results."""

    @execute.parallel
    def workerfn():
        with settings(abort_on_prompts=False):
            return operations.prompt("gimmie")

    results = execute.execute(workerfn, raise_unhandled_errors=False)
    expected = "EOF when reading a line"
    assert expected == str(results[0])


def test_execute_process_not_terminating(caplog):
    """we've had a case where a parallel process doesn't terminate despite the
    worker function having finished and returned a result.
    This test simulates that scenario (because I can't replicate it under test conditions)
    by patching `process_status` to always return `alive=True`"""

    # keep a reference before mock.patch overrides it
    orig_fn = execute.process_status

    def patch_fn(running_p):
        result = orig_fn(running_p)
        # why on earth are you *still* alive??
        result["alive"] = True
        return result

    @execute.parallel
    def worker_fn():
        return "foo"

    expected = "foo"

    with patch("threadbare.execute.process_status", new=patch_fn):
        results = execute.execute(worker_fn)
        assert [expected] == results

    # ensure a warning was logged

    _, log_level, log_msg = caplog.record_tuples[0]
    assert log_level == logging.WARNING

    expected_warning_text = "process is still alive despite worker having completed. terminating process: process--1"
    assert expected_warning_text == log_msg
