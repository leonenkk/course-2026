import pytest

from sentinel.audit import AuditStore
from sentinel.config import Settings
from sentinel.knowledge import HybridRetriever, load_runbooks
from sentinel.system import DEFAULT_RUNBOOKS
from sentinel.tools import default_registry


@pytest.fixture
def cfg():
    return Settings()


@pytest.fixture
def registry():
    return default_registry()


@pytest.fixture
def runbooks():
    return load_runbooks(DEFAULT_RUNBOOKS)


@pytest.fixture
def retriever(runbooks, cfg):
    return HybridRetriever(runbooks, cfg=cfg)


@pytest.fixture
def store():
    return AuditStore()
