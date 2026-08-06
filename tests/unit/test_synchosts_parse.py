import pytest

from lib.commands.synchosts import (
    PROPERTY_COLUMNS,
    CORE_COLUMNS,
    REQUIRED_COLUMNS,
    _parse_bool,
    _validate_host,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("web01.example.com", True),
        ("192.168.1.10", True),
        ("2001:db8::1", True),
        ("a" * 255, True),
        ("a" * 256, False),
        ("", False),
        ("has space", False),
        (None, False),
        ("with/tab\tchar", False),
    ],
)
def test_validate_host(value, expected):
    assert _validate_host(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("y", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("banana", False),
        ("", None),
        (None, None),
        ("  ", None),
    ],
)
def test_parse_bool(value, expected):
    assert _parse_bool(value) is expected


def test_property_columns_are_core_columns():
    assert PROPERTY_COLUMNS | {"host", "has_dr"} == CORE_COLUMNS


def test_required_columns_is_host_only():
    assert REQUIRED_COLUMNS == {"host"}


def test_property_columns_match_host_model():
    from lib.models import Host

    model_cols = set(Host.__table__.columns.keys())
    assert PROPERTY_COLUMNS | {"host", "has_dr"} <= model_cols
