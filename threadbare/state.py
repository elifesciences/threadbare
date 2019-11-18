import copy
import contextlib

ENV = {}

@contextlib.contextmanager
def settings(state=None, **kwargs):
    if state == None:
        state = ENV
    if not isinstance(state, dict):
        raise TypeError("state map must be a dictionary-like object, not %r" % type(state))
    original_values = copy.deepcopy(state)
    state.update(kwargs)
    try:
        yield state
    finally:
        state.clear()
        state.update(original_values)
