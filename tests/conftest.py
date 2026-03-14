import subprocess

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: integration tests (require claude CLI)")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("-m", default=None):
        skip = pytest.mark.skip(reason="integration tests require -m integration")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
