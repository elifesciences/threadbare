from functools import reduce

def first(x):
    try:
        return x[0]
    except (KeyError, ValueError, TypeError):
        return None

def merge(*dict_list):
    def reduce_fn(a, b=None):
        c = {}
        c.update(a)
        c.update(b or {})
        return c
    return reduce(reduce_fn, dict_list)

def subdict(d, key_list):
    key_list = key_list or []
    return {key: d[key] for key in key_list if key in d}

def update(d, k, v):
    d[k] = v
    return d

def identity(x):
    return x
