"""Histórico da apuração: registro, deduplicação, reinício, disco e a API da evolução."""
import json

import pytest

from app import historico as h
from app.historico import Historico, amostrar
from tests.conftest import popular_store


def resultado(st, votos, *, ts=1000, t="2026-10-04T19:00:00-03:00", divulga=True):
    """Resultado mínimo no formato de `parse_resultado`; `votos` = {sq: votos}."""
    total = sum(votos.values()) or 1
    return {
        "totalizado_em": t, "gerado_em": t, "estado": {"divulga": divulga},
        "secoes": {"st": st, "ts": ts, "pst": {"t": "x", "n": 100 * st / ts}},
        "candidatos": [{"sq": sq, "votos": v, "pct": {"t": "x", "n": 100 * v / total}} for sq, v in votos.items()],
    }


# ---- registro ------------------------------------------------------------------------------------------
def test_registra_pontos_novos_e_guarda_pct_de_cada_candidato():
    hist = Historico()
    assert hist.registrar("u:1:1:br", resultado(100, {"a": 60, "b": 40}))
    assert hist.registrar("u:1:1:br", resultado(200, {"a": 130, "b": 70, "c": 0}, t="2026-10-04T19:05:00-03:00"))
    s = hist.serie("u:1:1:br")
    assert [p["st"] for p in s] == [100, 200] and s[1]["t"] == "2026-10-04T19:05:00-03:00"
    assert s[0]["c"] == {"a": [60, 60.0], "b": [40, 40.0]}
    assert "c" not in s[1]["c"] and s[1]["pst"] == pytest.approx(20.0)  # quem tem 0 voto não entra
    assert hist.chaves() == ["u:1:1:br"]


def test_ignora_o_que_nao_e_novidade_ou_nao_pode_aparecer():
    hist = Historico()
    assert not hist.registrar("k", resultado(0, {"a": 0}))  # nada apurado
    assert not hist.registrar("k", resultado(100, {"a": 0}))  # seções sem votos liberados
    assert not hist.registrar("k", resultado(100, {"a": 50}, divulga=False))  # votação não liberada (dv='n')
    assert hist.registrar("k", resultado(100, {"a": 50}))
    assert not hist.registrar("k", resultado(100, {"a": 50}, t="2026-10-04T19:10:00-03:00"))  # regenerado sem mudar nada
    assert hist.registrar("k", resultado(100, {"a": 51}))  # mesmas seções, voto novo (retotalização): entra
    assert len(hist.serie("k")) == 2


def test_serie_recomeca_se_a_apuracao_voltar_muito_mas_tolera_pequenas_correcoes():
    hist = Historico()
    hist.registrar("k", resultado(800, {"a": 80}))
    hist.registrar("k", resultado(790, {"a": 79}))  # correção pequena: segue na mesma série
    assert [p["st"] for p in hist.serie("k")] == [800, 790]
    assert hist.registrar("k", resultado(100, {"a": 10}))  # voltou para 12%: é outra apuração (ex.: simulador reiniciado)
    assert [p["st"] for p in hist.serie("k")] == [100]


def test_series_de_chaves_diferentes_sao_independentes():
    hist = Historico()
    hist.registrar("u:1:1:br", resultado(10, {"a": 5}))
    hist.registrar("u:1:1:sp", resultado(10, {"a": 5}))
    hist.registrar("u:1:1:sp", resultado(20, {"a": 9}))
    assert len(hist.serie("u:1:1:br")) == 1 and len(hist.serie("u:1:1:sp")) == 2


def test_poda_quando_passa_do_maximo(monkeypatch):
    monkeypatch.setattr(h, "MAX_PONTOS", 20)
    hist = Historico()
    for i in range(1, 26):
        hist.registrar("k", resultado(i, {"a": i}))
    s = hist.serie("k")
    assert len(s) <= 20 and s[-1]["st"] == 25  # descarta os mais antigos, mantém o mais recente


# ---- disco ---------------------------------------------------------------------------------------------
def test_persiste_e_recarrega_apos_reiniciar(tmp_path):
    a = Historico(tmp_path)
    a.registrar("u:6257:1:br", resultado(100, {"a": 60, "b": 40}))
    a.registrar("u:6257:1:br", resultado(200, {"a": 130, "b": 70}))
    arquivo = tmp_path / "u_6257_1_br.jsonl"
    assert len(arquivo.read_text(encoding="utf-8").splitlines()) == 2
    b = Historico(tmp_path)  # o processo reiniciou
    assert [p["st"] for p in b.serie("u:6257:1:br")] == [100, 200]
    b.registrar("u:6257:1:br", resultado(300, {"a": 200, "b": 100}))
    assert [p["st"] for p in Historico(tmp_path).serie("u:6257:1:br")] == [100, 200, 300]


def test_linha_cortada_no_arquivo_e_ignorada(tmp_path):
    ok = json.dumps({"t": "x", "st": 5, "ts": 10, "pst": 50.0, "vv": 5, "c": {"a": [5, 100.0]}})
    (tmp_path / "u_1_1_br.jsonl").write_text(ok + "\n" + '{"t": "x", "st": 6, "c": {"a": [5, 1' + "\n" + "lixo\n", encoding="utf-8")
    assert [p["st"] for p in Historico(tmp_path).serie("u:1:1:br")] == [5]


def test_reinicio_da_serie_regrava_o_arquivo(tmp_path):
    hist = Historico(tmp_path)
    hist.registrar("k", resultado(800, {"a": 80}))
    hist.registrar("k", resultado(100, {"a": 10}))  # recomeçou
    assert [json.loads(l)["st"] for l in (tmp_path / "k.jsonl").read_text(encoding="utf-8").splitlines()] == [100]


# ---- amostragem ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("n, limite", [(10, 600), (600, 600), (601, 600), (5000, 600), (1000, 2)])
def test_amostrar_mantem_extremos_ordem_e_respeita_o_limite(n, limite):
    pontos = list(range(n))
    a = amostrar(pontos, limite)
    assert len(a) <= max(limite, 2) if n > limite else a == pontos
    assert a[0] == 0 and a[-1] == n - 1 and a == sorted(set(a))


# ---- API da evolução ---------------------------------------------------------------------------------------
def alimentar(store, passos=(0.1, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0)):
    for x in passos:
        popular_store(store, x)


def test_evolucao_dos_tres_primeiros_no_presidente(novo_app):
    app, store, _ = novo_app(0.05)
    alimentar(store)
    d = app.test_client().get("/api/v1/historico/presidente/br").get_json()
    assert d["slug"] == "presidente" and d["abr"] == "br" and d["n"] == 3 and d["total_pontos"] >= 7
    assert len(d["series"]) == 3 and len(d["pontos"]) == d["total_pontos"]
    assert all(len(s["pct"]) == len(d["pontos"]) == len(s["votos"]) for s in d["series"])
    pst = [p["pst"] for p in d["pontos"]]
    assert pst == sorted(pst) and pst[-1] == pytest.approx(100.0)  # a apuração só avança
    assert d["desde"] == d["pontos"][0]["t"]
    # são os 3 primeiros do ÚLTIMO ponto, em ordem de votos, e os votos finais fecham com o arquivo atual
    finais = [s["votos"][-1] for s in d["series"]]
    assert finais == sorted(finais, reverse=True)
    atual = {c["sq"]: c for c in app.test_client().get("/api/v1/presidente").get_json()["resultado"]["candidatos"]}
    for s in d["series"]:
        assert s["votos"][-1] == atual[s["sq"]]["votos"] and s["pct"][-1] == pytest.approx(atual[s["sq"]]["pct"]["n"])
        assert s["urna"] == atual[s["sq"]]["urna"] and s["cor"] == atual[s["sq"]]["cor"]
    assert [s["cor"] for s in d["series"]] != [0, 0, 0]  # as cores são as mesmas do ranking e do mapa


def test_evolucao_por_uf_e_parametro_n(novo_app):
    app, store, _ = novo_app(0.05)
    alimentar(store)
    c = app.test_client()
    gov = c.get("/api/v1/historico/governador/sp").get_json()
    assert gov["total_pontos"] >= 3 and len(gov["series"]) == 3 and gov["abr"] == "sp"  # UF que começa depois tem menos pontos
    assert len(c.get("/api/v1/historico/senador/ba?n=5").get_json()["series"]) == 5
    assert len(c.get("/api/v1/historico/presidente/sp?n=1").get_json()["series"]) == 1


def test_evolucao_antes_de_haver_votos_vem_vazia(novo_app):
    app, _, _ = novo_app(0.0)
    d = app.test_client().get("/api/v1/historico/presidente/br").get_json()
    assert d["total_pontos"] == 0 and d["pontos"] == [] and d["series"] == [] and d["desde"] is None


def test_evolucao_tem_etag_estavel_enquanto_nao_ha_ponto_novo(novo_app):
    app, store, _ = novo_app(0.2)
    alimentar(store, (0.3, 0.5))
    c = app.test_client()
    tag = c.get("/api/v1/historico/presidente/br").headers["ETag"]
    store.confirmar("u:6257:1:br")
    assert c.get("/api/v1/historico/presidente/br", headers={"If-None-Match": tag}).status_code == 304
    popular_store(store, 0.9)
    assert c.get("/api/v1/historico/presidente/br").headers["ETag"] != tag


@pytest.mark.parametrize("caminho, status", [
    ("/api/v1/historico/governador/br", 404), ("/api/v1/historico/prefeito/br", 404), ("/api/v1/historico/presidente/xx", 404),
    ("/api/v1/historico/presidente/zz", 200), ("/api/v1/historico/presidente/br?n=9", 400), ("/api/v1/historico/presidente/br?n=0", 400),
    ("/api/v1/historico/presidente/br?turno=2", 404), ("/api/v1/historico/senador/zz", 404),
])
def test_evolucao_valida_os_parametros(novo_app, caminho, status):
    app, _, _ = novo_app(0.5)
    assert app.test_client().get(caminho).status_code == status


def test_historico_sobrevive_a_reinicio_do_painel(tmp_path):
    from app import create_app
    from app.config import Settings
    from app.store import Store
    from app.tse.client import TokenBucket, TseClient
    from tests.conftest import SessaoTSE

    def subir():
        cliente = TseClient(user_agent="t", session=SessaoTSE(), bucket=TokenBucket(1000))
        store = Store()
        app = create_app(Settings(data_dir=tmp_path, iniciar_poller=False), store=store, client=cliente, iniciar_poller=False)
        return app, store

    app, store = subir()
    alimentar(store, (0.2, 0.5, 0.8))
    antes = app.test_client().get("/api/v1/historico/presidente/br").get_json()
    assert antes["total_pontos"] == 3
    app2, store2 = subir()  # reiniciou: o Store começa vazio, mas o histórico vem do disco
    popular_store(store2, 0.8)  # o poller recarrega o estado atual (mesmo conteúdo do último ponto: não duplica)
    depois = app2.test_client().get("/api/v1/historico/presidente/br").get_json()
    assert depois["total_pontos"] == 3 and depois["pontos"][0]["t"] == antes["pontos"][0]["t"]
    assert (tmp_path / "historico" / "simulado").is_dir() is False  # ambiente padrão é 'oficial'
    assert (tmp_path / "historico" / "oficial" / "u_6257_1_br.jsonl").exists()
