import copy
import contextlib

class LockableDict(dict):
    # unlocked by default
    # when multiprocessing starts a new process the ENV it has access to is not the same one
    # as the one here, nor is it in the same state
    read_only = False
    
    def __setitem__(self, key, val):
        if self.read_only:
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

@contextlib.contextmanager
def settings(state=None, **kwargs):
    if state == None:
        state = ENV
    if not isinstance(state, dict):
        raise TypeError("state map must be a dictionary-like object, not %r" % type(state))

    read_write(state)    
    original_values = copy.deepcopy(state)
    state.update(kwargs)
    try:
        yield state
    finally:
        read_only(state)
        state.clear()
        state.update(original_values)
