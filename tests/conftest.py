from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "tse" / "oficial"
AVATAR = (Path(__file__).parent.parent / "mock" / "avatar.jpeg").read_bytes()


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


# ---- app completo alimentado pelo simulador (sem rede) ---------------------------------------------------
class RespostaFalsa:
    def __init__(self, status=200, content=b"", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}


class SessaoTSE:
    """Faz de conta de `requests.Session`: devolve fotos válidas e 404 para o resto."""

    def __init__(self):
        self.chamadas: list[str] = []
        self.fotos_inexistentes: set[str] = set()

    def get(self, url, headers=None, timeout=None):
        self.chamadas.append(url)
        if "/fotos/" in url and not any(url.endswith(f"/{sq}.jpeg") for sq in self.fotos_inexistentes):
            return RespostaFalsa(200, AVATAR, {"Content-Type": "image/jpeg"})
        return RespostaFalsa(404)


def popular_store(store, x: float, *, cargos=(1, 3, 5)):
    """Carrega no Store tudo o que o poller carregaria, gerado pelo simulador parado em `x`."""
    from app.catalog import disputas_ativas, montar_alvos
    from app.tse import parse
    from app.tse.urls import TseUrls
    from mock import gerador
    from mock.gerador import Simulacao

    sim = Simulacao(duracao_s=100.0, inicio=x)
    sim.pausar()
    cfg = parse.parse_config_eleicoes(gerador.config_eleicoes(sim))
    store.guardar("cfg", "cfg", cfg, idg=cfg["idg"], etag=None, url="cfg")
    alvos = montar_alvos(disputas_ativas(cfg, cargos=cargos), lambda ciclo: TseUrls("http://x", "simulado", ciclo, cfg["dirs"]))
    for alvo in alvos:
        ele, abr = int(alvo.meta["ele"]), alvo.meta.get("abr")
        if alvo.tipo == "u":
            dados = parse.parse_resultado(gerador.resultado(sim, ele, alvo.meta["cargo"], abr))
        elif alvo.tipo == "ab":
            dados = parse.parse_acompanhamento(gerador.acompanhamento(sim, ele, abr))
        else:
            dados = parse.parse_municipios(gerador.municipios(sim, ele))
        store.guardar(alvo.chave, alvo.tipo, dados, idg=f"{dados['idg']}", etag=None, url=alvo.url, meta=alvo.meta)
    return sim


@pytest.fixture
def novo_app(tmp_path):
    """Fábrica: `novo_app(x)` devolve (flask_app, store, sessao) com dados do simulador em `x` (0 a 1)."""
    from app import create_app
    from app.config import Settings
    from app.store import Store
    from app.tse.client import TokenBucket, TseClient

    def criar(x: float = 0.5):
        sessao = SessaoTSE()
        cliente = TseClient(user_agent="teste", session=sessao, bucket=TokenBucket(1000))
        store = Store()
        app = create_app(Settings(data_dir=tmp_path, iniciar_poller=False), store=store, client=cliente, iniciar_poller=False)
        popular_store(store, x)
        return app, store, sessao

    return criar
