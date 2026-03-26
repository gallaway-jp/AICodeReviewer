import pytest


def ratio_is_close(actual, expected):
    return actual == pytest.approx(expected, rel=0.01)
