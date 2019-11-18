from functools import reduce

def first(x):
    "returns the first element in an collection of things"
    try:
        return x[0]
    except (KeyError, ValueError):
        return None

def merge(*dict_list):
    "non-destructively merges a series of dictionaries from left to right, returning a new dictionary"
    def reduce_fn(a, b=None):
        c = {}
        c.update(a)
        c.update(b or {})
        return c
    return reduce(reduce_fn, dict_list)

def subdict(d, key_list):
    "returns a subset of the given dictionary `d` for keys in `key_list`"
    key_list = key_list or []
    return {key: d[key] for key in key_list if key in d}
