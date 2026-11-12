import sys


def test_python_version_is_312_or_newer():
    assert sys.version_info >= (3, 12)


def test_pytest_runs():
    assert 1 + 1 == 2
