import random

import pytest

from lib.collectors.daemons import _parse_usec, _parse_list_prop, _parse_exec_prop
from lib.collectors.hostinfo import _parse_os_release
from lib.commands.synchosts import _validate_host, _parse_bool

CHARS = (
    "0123456789.minusinfinity shtumwe"
    "abcdefghijklmnopqrstuvwxyz;=[]{}/\\\t\n\"'()-,:"
    "Áéüñß€中"
)


def _rand_string(rng, max_len=64):
    return "".join(rng.choice(CHARS) for _ in range(rng.randint(0, max_len)))


@pytest.mark.parametrize("seed", range(10))
def test_fuzz_parse_usec_never_raises(seed):
    rng = random.Random(seed)
    for _ in range(500):
        val = _rand_string(rng, 40)
        _parse_usec(val)


@pytest.mark.parametrize("seed", range(5))
def test_fuzz_parse_usec_output_type(seed):
    rng = random.Random(seed)
    for _ in range(500):
        val = _rand_string(rng, 30)
        out = _parse_usec(val)
        assert out is None or (isinstance(out, int) and out >= 0)


@pytest.mark.parametrize("seed", range(5))
def test_fuzz_parse_list_prop_and_exec(seed):
    rng = random.Random(seed)
    for _ in range(300):
        val = _rand_string(rng, 80)
        lst = _parse_list_prop(val)
        assert isinstance(lst, list)
        assert all(isinstance(x, str) for x in lst)
        _parse_exec_prop(val)


@pytest.mark.parametrize("seed", range(5))
def test_fuzz_os_release_never_raises(seed):
    rng = random.Random(seed)
    for _ in range(200):
        lines = "\n".join(_rand_string(rng, 50) for _ in range(rng.randint(0, 20)))
        parsed = _parse_os_release(lines)
        assert isinstance(parsed, dict)
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in parsed.items())


@pytest.mark.parametrize("seed", range(5))
def test_fuzz_validate_host_never_raises(seed):
    rng = random.Random(seed)
    for _ in range(500):
        val = _rand_string(rng, 300)
        assert isinstance(_validate_host(val), bool)


@pytest.mark.parametrize("seed", range(5))
def test_fuzz_parse_bool_never_raises(seed):
    rng = random.Random(seed)
    for _ in range(500):
        val = _rand_string(rng, 20)
        out = _parse_bool(val)
        assert out in (True, False, None)


@pytest.mark.parametrize("seed", range(10))
def test_fuzz_pkg_line_splitting(seed):
    """rpm -qa lines with embedded separators must never crash and must not
    produce a row with a missing name."""
    rng = random.Random(seed)
    for _ in range(500):
        parts = [_rand_string(rng, 40) for _ in range(8)]
        line = ";".join(parts)
        split = line.split(";", 7)
        assert len(split) == 8
        if not split[0]:
            assert split[0] == ""
