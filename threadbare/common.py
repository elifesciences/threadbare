from functools import reduce

def first(x):
    "returns the first element in an collection of things"
    if x == None:
        return x
    try:
        if isinstance(x, dict):
            return list(x.items())[0]
        return x[0]
    except (ValueError, IndexError):
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
