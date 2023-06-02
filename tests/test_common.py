import pytest
from threadbare import common


def test_first():
    cases = [
        [None, None],
        ["", None],
        [[], None],
        [(), None],
        ["abc", "a"],
        [[1, 2, 3], 1],
        [(3, 2, 1), 3],
    ]
    for given, expected in cases:
        actual = common.first(given)
        assert expected == actual, "failed on case: %r => %r" % (expected, actual)


def test_first_bad_cases():
    dict_cases = [
        {},
        {1: 2},  # non-deterministic in all versions of python prior to 3.7
    ]
    for case in dict_cases:
        with pytest.raises(KeyError):
            common.first(case)


def test_merge():
    cases = [
        [[{}], {}],
        [[{}, {}], {}],
        [[{}, {}, {}], {}],
        [[{}, {"a": "b"}], {"a": "b"}],
        [[{"a": "b"}, {"a": "c"}], {"a": "c"}],
        [[{"a": "b"}, {"c": "d"}], {"a": "b", "c": "d"}],
    ]
    for arg_list, expected in cases:
        actual = common.merge(*arg_list)
        assert expected == actual, "failed on case: %r => %r" % (expected, actual)


def test_subdict():
    cases = [
        [{}, [], {}],
        [{}, ["a"], {}],
        [{"a": "b"}, ["a"], {"a": "b"}],
        [{"a": "b", "c": "d", "e": "f"}, ["a", "e"], {"a": "b", "e": "f"}],
    ]
    for d, key_list, expected in cases:
        actual = common.subdict(d, key_list)
        assert expected == actual


def test__shell_escape():
    cases = [["", ""], ["$abc", "\\$abc"], ['"', '\\"'], ["`", "\\`"]]
    for given, expected in cases:
        actual = common._shell_escape(given)
        assert expected == actual


def test__shell_escape_bad_cases():
    bad_types = [[None, TypeError], [b"", TypeError]]
    for given, expected in bad_types:
        with pytest.raises(expected):
            common._shell_escape(given)


def test_is_int():
    true_cases = [1, 2, 3, 4, 5, -1, -2, -3, -4]
    for case in true_cases:
        assert common.isint(case)
    false_cases = [None, "", [], {}]
    for case in false_cases:
        assert not common.isint(case)
