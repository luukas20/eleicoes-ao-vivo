import requests

from app.tse.client import STATUS_DISJUNTOR, STATUS_REDE, Breaker, TokenBucket, TseClient


class FakeResp:
    def __init__(self, status=200, body=b"{}", headers=None):
        self.status_code, self.content, self.headers = status, body, headers or {}


class FakeSession:
    """Devolve respostas em fila e guarda as requisições feitas."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def get(self, url, headers=None, timeout=None):
        self.chamadas.append((url, dict(headers or {})))
        r = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(r, Exception):
            raise r
        return r


def cliente(*respostas, **kw):
    sessao = FakeSession(*respostas)
    kw.setdefault("bucket", TokenBucket(1000))
    return TseClient(user_agent="teste", session=sessao, **kw), sessao


def test_200_traz_corpo_etag_e_max_age():
    c, _ = cliente(FakeResp(200, b'{"a":1}', {"ETag": '"abc"', "Last-Modified": "Fri, 02 Oct 2026 21:31:27 GMT", "Cache-Control": "max-age=31"}))
    r = c.get("https://x.test/a.json")
    assert r.ok and r.body == b'{"a":1}'
    assert (r.etag, r.max_age, r.last_modified) == ('"abc"', 31, "Fri, 02 Oct 2026 21:31:27 GMT")


def test_get_condicional_envia_etag_e_last_modified_e_304_vem_sem_corpo():
    c, sessao = cliente(FakeResp(304, b"ignorado", {"ETag": '"abc"'}))
    r = c.get("https://x.test/a.json", etag='"abc"', last_modified="Fri, 02 Oct 2026 21:31:27 GMT")
    assert r.not_modified and r.body == b""
    enviados = sessao.chamadas[0][1]
    assert enviados["If-None-Match"] == '"abc"'
    assert enviados["If-Modified-Since"] == "Fri, 02 Oct 2026 21:31:27 GMT"


def test_sem_validadores_nao_envia_cabecalhos_condicionais():
    c, sessao = cliente(FakeResp(200))
    c.get("https://x.test/a.json")
    assert sessao.chamadas[0][1] == {}


def test_403_ou_429_abre_o_disjuntor_e_para_de_enviar():
    c, sessao = cliente(FakeResp(429))
    assert c.get("https://x.test/a.json").status == 429
    assert c.breaker.restante() > 10 * 60  # bloqueio do TSE é de 10 min; esperamos mais
    r = c.get("https://x.test/b.json")
    assert r.status == STATUS_DISJUNTOR and r.retry_after > 0
    assert len(sessao.chamadas) == 1  # a segunda nem saiu


def test_excesso_de_404_abre_o_disjuntor():
    c, sessao = cliente(FakeResp(404), breaker=Breaker(max_404_por_min=3, pausa_404_s=120))
    status = [c.get(f"https://x.test/{i}.json").status for i in range(6)]
    assert status[:4] == [404, 404, 404, 404]  # o 4º 404 estoura a cota de 3 por minuto
    assert status[4] == STATUS_DISJUNTOR
    assert len(sessao.chamadas) == 4


def test_falha_de_rede_vira_status_zero_com_erro():
    c, _ = cliente(requests.ConnectionError("sem rede"))
    r = c.get("https://x.test/a.json")
    assert r.status == STATUS_REDE and "ConnectionError" in r.error
    assert c.metrics.snapshot()["ultimo_erro"].startswith("ConnectionError")


def test_metricas_contam_por_status():
    c, _ = cliente(FakeResp(200, b"abc"))
    c.get("https://x.test/a.json")
    c.get("https://x.test/a.json")
    snap = c.metrics.snapshot()
    assert snap["total"] == 2 and snap["por_status"] == {"200": 2} and snap["bytes_recebidos"] == 6


def test_token_bucket_espaca_as_requisicoes():
    t = [0.0]
    esperas = []

    def dormir(s):
        esperas.append(s)
        t[0] += s

    bucket = TokenBucket(rate=10, burst=2, clock=lambda: t[0], sleep=dormir)
    for _ in range(5):
        bucket.acquire()
    # 2 de rajada imediata; as 3 seguintes esperam ~0,1 s cada (10/s) => 0,3 s no total
    assert len(esperas) >= 3
    assert abs(sum(esperas) - 0.3) < 1e-6
