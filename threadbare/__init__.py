from collections.abc import Iterable
import uuid
import contextlib
from multiprocessing import Process, Queue
import os, time

ENV = {}

@contextlib.contextmanager
def settings(state=None, **kwargs):
    if state == None:
        state = ENV
    if not isinstance(state, dict):
        raise TypeError("state map must be a dictionary-like object, not %r" % type(state))
    original = {}
    for key, val in kwargs.items():
        if key in state:
            original[key] = state[key]
        state[key] = val
    try:
        yield state
    finally:
        for key, val in kwargs.items():
            if key in original:
                state[key] = original[key]
            else:
                del state[key]

def parallel(env, func, pool_size=None):
    """Forces the wrapped function to run in parallel, instead of sequentially.
    This is an opportunity for pre/post process work prior to calling a function in parallel."""
    # https://github.com/mathiasertl/fabric/blob/master/fabric/decorators.py#L164-L194

    def inner(*args, **kwargs):
        # wrap this in a `settings` with given env? otherwise, why are we passing env?
        return func(*args, **kwargs)

    inner.parallel = True # `func` *must* be forced to run in parallel to main process

    # when None, executor decides how many instances of `func` to execute (1, probably)
    # if set and executor is given a set of values to use instead, `pool_size` is ignored
    inner.pool_size = pool_size if pool_size else None 
    
    return inner

def _parallel_execution_worker_wrapper(env, worker_func, name, queue):
    try:
        # Fabric is nuking the child process's env dictionary
        # https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L229-L237

        # what we can do is say that worker functions executed in parallel must use the
        # implicit `settings() as env` invocation rather than `settings(env)` as we have
        # no reference to `env` unless the worker function accepts it as a parameter.
        # and we can't rely on that.
        if env:
            ENV.update(env)
        result = worker_func()
        queue.put({'name': name, 'result': result})
    except BaseException as unhandled_exception:
        queue.put({'name': name, 'result': unhandled_exception})

def unique_id():
    return str(uuid.uuid4())

def _parallel_execution(env, func, param_key, param_values):

    # in Fabric, `execute` is a guard-type function that ensures the function and the function's environment is correct
    # before passing it to `_execute` that does the actual magic.
    # `execute`: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L372-L401
    # `_execute`: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L213-L277

    # the custom 'JobQueue' adds complexity but can be avoided (I hope):
    # https://github.com/mathiasertl/fabric/blob/master/fabric/job_queue.py

    results_q = Queue()
    kwargs = {
        'env': env,
        'worker_func': func,
        #'name': None, # a name is assigned on process start
        'queue': results_q,
    }
    pool_values = param_values or range(0, getattr(func, 'pool_size', 1))
        
    pool = []
    for idx, n in enumerate(pool_values):
        kwargs['name'] = 'process--' + str(idx + 1) # process--1, process--2
        new_env = env.copy()
        if n:
            new_env[param_key] = n
        kwargs['env'] = new_env
        p = Process(name=kwargs['name'], target=_parallel_execution_worker_wrapper, kwargs=kwargs)
        p.start()
        pool.append(p)
        
    def status(running_p):
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
            result['kill-signal'] = running_p.exitcode
        return result

    result_map = {} # {process-name: process-results, ...}

    #print('pool', list(map(status, pool)))
    
    # poll the processes until all are complete
    # remove process from pool when it is complete
    while len(pool) > 0:
        for idx, running_p in enumerate(pool):
            result = status(running_p)
            if not result['alive']:
                result_map[result['name']] = result
                del pool[idx]
        time.sleep(0.1)
        
    # all processes are complete
    # empty the queue and marry the results to their process results using their 'name'

    while not results_q.empty():
        job_result = results_q.get()
        # print('got job', job_result)
        job_name = job_result['name']
        result_map[job_name]['result'] = job_result['result']

    return list(result_map.values())

def _serial_execution(env, func, param_key, param_values):
    result_list = []
    if param_key and param_values:
        for x in param_values:
            with settings(env, **{param_key: x}):
                result_list.append(func())
    else:
        # pretty boring :(
        with settings(env):
            result_list.append(func())
    return result_list

def execute(env, func, param_key=None, param_values=None):
    """inspects a given function and then executes it either serially or in another process using Python's `multiprocessing` module.
    `param` and `param_list` control the number of processes spawned and the name of the parameter passed to the function.

    For example:

        execute({}, somefunc, param_key='host', param_values=['127.0.0.1', '127.0.1.1', 'localhost'])

    will ensure that `somefunc` has the (local) state property 'host' with a value of one of the above when executed.

    `param` and `param_list` are optional, but if one is specified then so must the other.

    parent process blocks until all child processes have completed or timeout is reached.
    returns a map of execution data with the return values of the individual executions available under 'result'"""

    # in Fabric, `execute` is a guard-type function that ensures the function and the function's environment is correct
    # before passing it to `_execute` that does the actual magic.
    # `execute`: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L372-L401
    # `_execute`: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L213-L277

    # the custom 'JobQueue' adds complexity but can be avoided (I hope):
    # https://github.com/mathiasertl/fabric/blob/master/fabric/job_queue.py
    
    if (param_key and not param_values) or \
       (not param_key and param_values):
        raise ValueException("either a `param_key` AND `param_values` are provided OR neither are provided")

    if param_values and not isinstance(param_values, Iterable):
        raise ValueError("given value for `param_values` must be an iterable type, not %r" % type(param_values))

    if param_key and not isinstance(param_key, str):
        raise ValueError("given value for `param_key` must be a valid function parameter key")
    
    if hasattr(func, 'parallel') and func.parallel:
        result_list = _parallel_execution(env, func, param_key, param_values)
        return [result['result'] for result in result_list]
    return _serial_execution(env, func, param_key, param_values)
