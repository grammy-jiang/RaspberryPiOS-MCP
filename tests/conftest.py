"""
Pytest configuration for the Raspberry Pi MCP Server tests.
"""

import pytest

# Configure pytest-asyncio mode
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
    )


# Configure collection to avoid warning about TestingConfig
collect_ignore_glob = []
