import contextlib

ENV = {}

@contextlib.contextmanager
def settings(state=None, **kwargs):
    if state == None:
        state = ENV
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
