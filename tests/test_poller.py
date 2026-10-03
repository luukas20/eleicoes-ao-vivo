import hashlib
import json
import random

import pytest

from app.catalog import Alvo
from app.config import Settings
from app.poller import ESPERA_404_S, Poller, _ExecutorSincrono
from app.store import Store
from app.tse.client import STATUS_DISJUNTOR, STATUS_REDE, Breaker, Metrics, Response, TokenBucket
from app.tse.urls import TseUrls

URLS = TseUrls("https://resultados.tse.jus.br", "oficial", "ele2026")
BR = "u:6257:1:br"


class ClienteFalso:
    """Serve os fixtures por URL; o que não existe dá 404, como no TSE."""

    def __init__(self, arquivos):
        self.arquivos = dict(arquivos)
        self.override: dict[str, Response] = {}
        self.chamadas: list[str] = []
        self.max_age = None
        self.metrics, self.breaker, self.bucket = Metrics(), Breaker(), TokenBucket(1000)

    def get(self, url, *, etag=None, last_modified=None):
        self.chamadas.append(url)
        if url in self.override:
            return self.override[url]
        corpo = self.arquivos.get(url)
        if corpo is None:
            return Response(url, 404)
        et = '"' + hashlib.md5(corpo).hexdigest() + '"'
        if etag == et:
            return Response(url, 304, etag=et)
        return Response(url, 200, body=corpo, etag=et, max_age=self.max_age)


@pytest.fixture
def cenario(fixture_bytes):
    arquivos = {
        URLS.config_eleicoes(): fixture_bytes("comum/config/ele-c.json"),
        URLS.resultado(6257, 1, "br"): fixture_bytes("ele2026/6257/dados/br/br-c0001-e006257-u.json"),
        URLS.resultado(6257, 1, "zz"): fixture_bytes("ele2026/6257/dados/zz/zz-c0001-e006257-u.json"),
        URLS.acompanhamento(6257, "br"): fixture_bytes("ele2026/6257/dados/br/br-e006257-ab.json"),
        URLS.resultado(6259, 3, "sp"): fixture_bytes("ele2026/6259/dados/sp/sp-c0003-e006259-u.json"),
    }
    cliente = ClienteFalso(arquivos)
    t = [1000.0]
    store = Store(relogio=lambda: t[0])
    poller = Poller(
        Settings(iniciar_poller=False, cargos=(1, 3, 5, 6, 7, 8)), cliente, store,
        relogio=lambda: t[0], aleatorio=random.Random(7), executor=_ExecutorSincrono(),
    )

    class Cenario:
        pass

    c = Cenario()
    c.poller, c.cliente, c.store, c.t = poller, cliente, store, t
    c.avancar = lambda segundos: (t.__setitem__(0, t[0] + segundos), poller._tick())
    poller._adicionar(poller._alvo_config(), inicio_imediato=True)
    poller._tick()  # busca o EA11 e sincroniza os alvos
    return c


def test_config_cria_os_alvos_derivados(cenario):
    assert cenario.store.get("cfg").idg == "980407"
    assert len(cenario.poller._estados) == 1 + 141  # EA11 + (2 EA12 + 2 EA14 + 137 EA20)
    # nada foi consultado além do EA11 até o intervalo de espalhamento passar
    assert cenario.cliente.chamadas == [URLS.config_eleicoes()]


def test_busca_o_que_existe_e_trata_404_com_espera_longa(cenario):
    cenario.avancar(1000)
    assert cenario.store.get(BR).idg == "1026910"
    assert cenario.store.get("ab:6257:br").idg == "962221"
    assert cenario.store.get("u:6259:3:sp").dados["abrangencia"] == {"tipo": "uf", "codigo": "sp"}
    assert cenario.store.get("u:6257:1:zz") is not None

    inexistente = cenario.poller._estados["u:6259:5:mg"]  # não está nos fixtures: 404
    assert inexistente.ultimo_status == 404 and "404" in inexistente.ultimo_erro
    assert inexistente.proxima - cenario.t[0] >= ESPERA_404_S * 0.9
    assert cenario.store.get("u:6259:5:mg") is None


def test_sem_mudanca_o_intervalo_recua_ate_o_teto_e_usa_304(cenario):
    cenario.avancar(1000)
    estado = cenario.poller._estados[BR]
    assert estado.intervalo == 8  # piso da camada 'nacional', logo após dado novo
    intervalos = []
    for _ in range(4):
        cenario.avancar(25)
        intervalos.append(estado.intervalo)
    assert intervalos == [12, 18, 20, 20]  # x1,5 até o teto de 20 s
    assert estado.ultimo_status == 304
    assert cenario.store.get(BR).obtido_em == cenario.t[0]  # 304 renova a confirmação


def test_nova_geracao_guarda_e_volta_ao_piso(cenario):
    cenario.avancar(1000)
    for _ in range(3):
        cenario.avancar(25)
    estado, versao = cenario.poller._estados[BR], cenario.store.versao
    assert estado.intervalo == 20

    novo = json.loads(cenario.cliente.arquivos[URLS.resultado(6257, 1, "br")].decode("utf-8"))
    novo["idg"] = "1026911"
    novo["and"] = "p"
    cenario.cliente.arquivos[URLS.resultado(6257, 1, "br")] = json.dumps(novo).encode("utf-8")
    cenario.avancar(25)

    snap = cenario.store.get(BR)
    assert snap.idg == "1026911" and snap.dados["estado"]["andamento"] == "p"
    assert cenario.store.versao == versao + 1
    assert estado.intervalo == 8  # mudou: volta ao piso


def test_max_age_do_cdn_e_respeitado_ate_o_teto(cenario):
    cenario.cliente.max_age = 15
    cenario.avancar(1000)
    assert cenario.poller._estados[BR].intervalo == 15  # piso 8, mas o CDN pediu 15
    cenario.cliente.max_age = 600
    cenario.cliente.arquivos[URLS.resultado(6257, 1, "br")] += b" "  # força um 200 com idg igual
    cenario.avancar(30)
    assert cenario.poller._estados[BR].intervalo <= 20  # nunca passa do teto da camada


def test_falha_de_rede_recua_exponencialmente_e_recupera(cenario):
    url = URLS.resultado(6257, 1, "br")
    cenario.cliente.override[url] = Response(url, STATUS_REDE, error="ConnectionError: x")
    estado = cenario.poller._estados[BR]
    esperas = []
    for _ in range(3):
        cenario.avancar(1000)
        esperas.append(round((estado.proxima - cenario.t[0]) / 5))  # ~5, ~10, ~20 s (jitter de 10%)
    assert estado.falhas == 3 and "ConnectionError" in estado.ultimo_erro
    assert esperas == [1, 2, 4]

    del cenario.cliente.override[url]
    cenario.avancar(1000)
    assert estado.falhas == 0 and estado.ultimo_erro is None and cenario.store.get(BR) is not None


def test_disjuntor_aberto_adia_pelo_retry_after(cenario):
    url = URLS.resultado(6257, 1, "br")
    cenario.cliente.override[url] = Response(url, STATUS_DISJUNTOR, error="disjuntor aberto", retry_after=300)
    cenario.avancar(1000)
    estado = cenario.poller._estados[BR]
    assert estado.proxima - cenario.t[0] >= 270 and estado.falhas == 0


def test_json_invalido_nao_derruba_o_poller(cenario):
    url = URLS.resultado(6257, 1, "br")
    cenario.cliente.override[url] = Response(url, 200, body=b"<html>erro</html>")
    cenario.avancar(1000)
    estado = cenario.poller._estados[BR]
    assert estado.falhas == 1 and estado.ultimo_erro and cenario.store.get(BR) is None
    assert cenario.store.get("ab:6257:br") is not None  # os demais alvos seguem normais


def test_alvo_sob_demanda_expira_sem_renovacao(cenario):
    alvo = Alvo("u:6257:1:sp:71072", "u", URLS.resultado(6257, 1, "sp", municipio=71072), "sob_demanda", {})
    cenario.poller.solicitar(alvo, ttl=90)
    assert "u:6257:1:sp:71072" in cenario.poller._estados
    cenario.avancar(60)
    cenario.poller.solicitar(alvo, ttl=90)  # renovado
    cenario.avancar(60)
    assert "u:6257:1:sp:71072" in cenario.poller._estados
    cenario.avancar(200)  # ninguém renovou
    assert "u:6257:1:sp:71072" not in cenario.poller._estados


def test_estado_para_a_pagina_de_status(cenario):
    cenario.avancar(1000)
    s = cenario.poller.estado()
    assert s["alvos"] == 142 and set(s["camadas"]) >= {"config", "nacional", "uf", "uf_lento", "estatico"}
    assert s["cliente"]["disjuntor"]["aberto"] is False and "req_por_s" in s["cliente"]
    # 4 arquivos existem nos fixtures (BR, exterior, EA14, Governador-SP), o EA11 já veio e dá 304; o resto é 404
    assert s["ultimo_status_por_alvo"] == {"200": 4, "304": 1, "404": 137}
    assert s["total_com_problema"] == 137 and len(s["com_problema"]) == 50  # lista limitada; total completo
