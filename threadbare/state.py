import copy
import contextlib

CLEANUP_KEY = "_cleanup"

class LockableDict(dict):
    # unlocked by default
    # when multiprocessing starts a new process the ENV it has access to is not the same one
    # as the one here, nor is it in the same state
    read_only = False
    
    def __setitem__(self, key, val):
        #exceptions = [CLEANUP_KEY]
        if self.read_only: # and key not in exceptions:
            raise ValueError("dictionary is locked attempting to write %r with %r" % (key, val))
        dict.__setitem__(self, key, val)

def read_only(d):
    if hasattr(d, 'read_only'):
        d.read_only = True

def read_write(d):
    if hasattr(d, 'read_only'):
        d.read_only = False

ENV = LockableDict()
read_only(ENV)

def cleanup(old_env):
    if True:
        return
    if CLEANUP_KEY in old_env:
        for cleanup_fn in old_env[CLEANUP_KEY]:
            cleanup_fn()
        del old_env[CLEANUP_KEY]

def add_cleanup(fn):
    if True:
        return
    cleanup_fn_list = ENV.get(CLEANUP_KEY, [])
    cleanup_fn_list.append(fn)
    ENV[CLEANUP_KEY] = cleanup_fn_list

def deepish_copy(x):
    if isinstance(x, dict):
        return {k: deepish_copy(v) for k, v in x.items()}
    if isinstance(x, list):
        return [deepish_copy(v) for v in x]

    return copy.copy(x)

@contextlib.contextmanager
def settings(state=None, **kwargs):
    if state == None:
        state = ENV
    if not isinstance(state, dict):
        raise TypeError("state map must be a dictionary-like object, not %r" % type(state))

    read_write(state)
    #original_values = copy.deepcopy(state)
    original_values = deepish_copy(state)
    state.update(kwargs)
    #if CLEANUP_KEY in state:
    #    state.update({CLEANUP_KEY: []})
    try:
        yield state
    finally:
        cleanup(state)
        read_only(state)
        state.clear()
        state.update(original_values)
