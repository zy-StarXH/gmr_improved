import csv
from pathlib import Path

import pytest

from gmr_improved.contact_audit import _as_bool, _as_optional_float


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("True", True), ("false", False), (" TRUE ", True)],
)
def test_as_bool(raw: str, expected: bool) -> None:
    assert _as_bool(raw) is expected


def test_as_bool_rejects_ambiguous_value() -> None:
    with pytest.raises(ValueError, match="Invalid diagnostic boolean"):
        _as_bool("1")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", None), ("None", None), (" 0.125 ", 0.125)],
)
def test_as_optional_float(raw: str, expected: float | None) -> None:
    assert _as_optional_float(raw) == expected
