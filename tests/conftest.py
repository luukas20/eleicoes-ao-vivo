from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "tse" / "oficial"


@pytest.fixture(scope="session")
def fixture_bytes():
    """Lê um fixture real do TSE (caminho relativo a tests/fixtures/tse/oficial)."""

    def carregar(relativo: str) -> bytes:
        return (FIXTURES / relativo).read_bytes()

    return carregar


@pytest.fixture(scope="session")
def fixture_json(fixture_bytes):
    from app.tse.parse import decodificar

    def carregar(relativo: str) -> dict:
        return decodificar(fixture_bytes(relativo))

    return carregar
