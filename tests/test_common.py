from threadbare import common

def test_first():
    cases = [
        [None, None],
        ["", None],
        [[], None],
        [(), None],
        [{}, None],

        ["abc", "a"],
        [[1, 2, 3], 1],
        [(3, 2, 1), 3],
        [{1: 2}, (1, 2)], # non-deterministic in most versions of python, don't do this
    ]
    for given, expected in cases:
        actual = common.first(given)
        assert expected == actual, "failed on case: %r => %r" % (expected, actual)

def test_merge():
    cases = [
        [[{}], {}],
        [[{}, {}], {}],
        [[{}, {}, {}], {}],

        [[{}, {'a': 'b'}], {'a': 'b'}],
        [[{'a': 'b'}, {'a': 'c'}], {'a': 'c'}],
        [[{'a': 'b'}, {'c': 'd'}], {'a': 'b', 'c': 'd'}],
    ]
    for arg_list, expected in cases:
        actual = common.merge(*arg_list)
        assert expected == actual, "failed on case: %r => %r" % (expected, actual)
    
def test_subdict():
    cases = [
        [{}, [], {}],
        [{}, ['a'], {}],
        [{'a': 'b'}, ['a'], {'a': 'b'}],
        [{'a': 'b', 'c': 'd', 'e': 'f'}, ['a', 'e'], {'a': 'b', 'e': 'f'}],
    ]
    for d, key_list, expected in cases:
        actual = common.subdict(d, key_list)
        assert expected == actual
