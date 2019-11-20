import copy
from multiprocessing import Process, Queue
import time
from threadbare.common import first
from threadbare import state

def serial(func, pool_size=None):
    """Forces the given function to run `pool_size` times.
    when pool_size is None (default), executor decides how many instances of `func` to execute (1, probably).
    if set and executor is given a set of values to use instead, `pool_size` is ignored"""
    def inner(*args, **kwargs):
        return func(*args, **kwargs)
    inner.pool_size = pool_size
    return inner

def parallel(func, pool_size=None):
    """Forces the wrapped function to run in parallel, instead of sequentially.
    This is an opportunity for pre/post process work prior to calling a function in parallel."""
    # https://github.com/mathiasertl/fabric/blob/master/fabric/decorators.py#L164-L194
    wrapped_func = serial(func, pool_size)
    wrapped_func.parallel = True # `func` *must* be forced to run in parallel to main process
    return wrapped_func

def _parallel_execution_worker_wrapper(env, worker_func, name, queue):
    try:
        # Fabric is nuking the child process's env dictionary
        # https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L229-L237

        # what we can do is say that worker functions executed in parallel must use the
        # implicit `settings() as env` invocation rather than `settings(env)` as we have
        # no reference to `env` unless the worker function accepts it as a parameter.
        # and we can't rely on that.
        if env:
            state.ENV.update(env)
        result = worker_func()
        queue.put({'name': name, 'result': result})
    except BaseException as unhandled_exception:
        # "Note that exit handlers and finally clauses, etc., will not be executed."
        # - https://docs.python.org/2/library/multiprocessing.html#multiprocessing.Process.terminate
        queue.put({'name': name, 'result': unhandled_exception})

def process_status(running_p):
    # https://docs.python.org/2/library/multiprocessing.html#process-and-exceptions
    result = {'pid': running_p.pid,
              'name': running_p.name,
              'exitcode': running_p.exitcode,
              'alive': running_p.is_alive(),
              'killed': False,
              'kill-signal': None
    }
    if running_p.exitcode != None and running_p.exitcode < 0:
        result['killed'] = True
        result['kill-signal'] = -running_p.exitcode
    return result

def _parallel_execution(env, func, param_key, param_values, return_process_pool=False):
    "executes the given function in parallel to main process. blocks until processes are complete"
    results_q = Queue()
    kwargs = {
        #'env': ..., # each process will get a new state dictionary
        'worker_func': func,
        #'name': ..., # a name is assigned on process start
        'queue': results_q,
    }
    pool_size = getattr(func, 'pool_size', None)
    pool_size = pool_size if pool_size != None else 1
    pool_values = param_values or range(0, pool_size)
        
    pool = []
    for idx, n in enumerate(pool_values):
        kwargs['name'] = 'process--' + str(idx + 1) # process--1, process--2
        new_env = {} if not env else copy.deepcopy(env)
        if n:
            new_env[param_key] = n
        kwargs['env'] = new_env
        p = Process(name=kwargs['name'], target=_parallel_execution_worker_wrapper, kwargs=kwargs)
        p.start()
        pool.append(p)

    if return_process_pool:
        # don't poll for results, don't wait to finish, just return the list of running processes
        return results_q, pool

    result_map = {} # {process-name: process-results, ...}

    # poll the processes until all are complete
    # remove process from pool when it is complete
    while len(pool) > 0:
        for idx, running_p in enumerate(pool):
            result = process_status(running_p)
            if not result['alive']:
                result_map[result['name']] = result
                del pool[idx]
        time.sleep(0.1)
        
    # all processes are complete
    # empty the queue and marry the results to their process results using their 'name'

    while not results_q.empty():
        job_result = results_q.get()
        job_name = job_result['name']
        result_map[job_name]['result'] = job_result['result']

    results_q.close()

    # sort the results, drop the process name
    return [b for a, b in sorted(result_map.items(), key=first)]

def _serial_execution(env, func, param_key, param_values):
    "executes the given function serially"
    result_list = []
    if param_key and param_values:
        for x in param_values:
            with state.settings(env, **{param_key: x}):
                result_list.append(func())
    else:
        # pretty boring :(
        # I could set '_idx' or something in `env` I suppose ..
        for _ in range(0, getattr(func, 'pool_size', 1)):
            with state.settings(env):
                result_list.append(func())
    return result_list

def execute(env, func, param_key=None, param_values=None):
    """inspects a given function and then executes it either serially or in another process using Python's `multiprocessing` module.
    `param` and `param_list` control the number of processes spawned and the name of the parameter passed to the function.

    For example:

        execute({}, somefunc, param_key='host', param_values=['127.0.0.1', '127.0.1.1', 'localhost'])

    will ensure that `somefunc` has the (local) state property 'host' with a value of one of the above when executed.

    `param` and `param_list` are optional, but if one is specified then so must the other.

    parent process blocks until all child processes have completed.
    returns a map of execution data with the return values of the individual executions available under 'result'"""

    # in Fabric, `execute` is a guard-type function that ensures the function and the function's environment is correct
    # before passing it to `_execute` that does the actual magic.
    # `execute`: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L372-L401
    # `_execute`: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L213-L277

    # the custom 'JobQueue' adds complexity but can be avoided (I hope):
    # https://github.com/mathiasertl/fabric/blob/master/fabric/job_queue.py
    
    if (param_key and param_values == None) or \
       (param_key == None and param_values):
        raise ValueError("either a `param_key` AND `param_values` are provided OR neither are provided")

    if param_values != None and type(param_values) not in [list, tuple, set]:
        raise ValueError("given value for `param_values` must be an iterable type, not %r" % type(param_values))

    if param_key != None and not isinstance(param_key, str):
        raise ValueError("given value for `param_key` must be a valid function parameter key")
    
    if hasattr(func, 'parallel') and func.parallel:
        result_list = _parallel_execution(env, func, param_key, param_values)
        return [result['result'] for result in result_list]
    return _serial_execution(env, func, param_key, param_values)

def execute_with_hosts(env, func, hosts=None):
    "convenience wrapper around `execute`. calls `execute` on given `func` but uses `all_hosts`  "
    with state.settings(env):
        host_list = hosts or env.get('hosts') or []
        # Fabric may know about many hosts ('all_hosts') but only be acting upon a subset of them ('hosts')
        # https://github.com/mathiasertl/fabric/blob/master/sites/docs/usage/env.rst#all_hosts
        # it says 'for informational purposes only' so I'm going to disable for now
        #env['all_hosts'] = env['hosts']
        return execute(env, func, param_key='host_string', param_values=host_list)