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
    This is an opportunity for pre/process work prior to calling a function in parallel."""
    # https://github.com/mathiasertl/fabric/blob/master/fabric/decorators.py#L164-L194

    def inner(*args, **kwargs):
        return func(*args, **kwargs)

    inner.parallel = True # `func` *must* be forced to run in parallel to main process
    inner.pool_size = pool_size if pool_size else None # when None, executor decides how many instances of `func` to execute
    
    return inner

def _execute(env, func, name, queue):
    result = func()
    queue.put({'name': name, 'result': result})
    return result


def unique_id():
    return str(uuid.uuid4())

def execute(env, func):
    """inspects a given function and then executes it either serially or in another process using Python's `multiprocessing` module.
    blocks until all processes have completed or timeout is reached
    """

    # in Fabric, `execute` is a guard-type function that ensures the function and the function's environment is correct
    # before passing it to `_execute` that does the actual magic.
    # `execute`: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L372-L401
    # `_execute`: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L213-L277

    # the custom 'JobQueue' adds complexity but can be avoided (I hope):
    # https://github.com/mathiasertl/fabric/blob/master/fabric/job_queue.py

    q = Queue()
    kwargs = {
        'env': env,
        'func': func,
        #'name': None, # a name is assigned on process start
        'queue': q,
    }
    pool_size = getattr(func, 'pool_size', 1)
    pool = []
    for n in range(0, pool_size):
        kwargs['name'] = unique_id()
        p = Process(name=kwargs['name'], target=_execute, kwargs=kwargs)
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

    return_list = []
    while not q.empty():
        job_result = q.get()
        # print('got job', job_result)
        job_name = job_result['name']
        result_map[job_name]['result'] = job_result['result']
        return_list.append(job_result['result'])

    #return list(result_map.values())
    return return_list
