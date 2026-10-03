"""Testes do simulador do TSE (dados fictícios) e da integração poller <-> simulador."""
import threading
import time

import pytest
from werkzeug.serving import make_server

from app.config import Settings
from app.poller import Poller
from app.store import Store
from app.tse import parse as p
from app.tse.client import TseClient
from app.tse.dominio import BRASIL, EXTERIOR, UFS
from mock import gerador
from mock.gerador import PASSOS, Simulacao, pct
from mock.server import criar_app


def sim_em(x: float) -> Simulacao:
    """Simulação parada em x (fração da apuração), sem depender do relógio."""
    s = Simulacao(duracao_s=100.0, inicio=x)
    s.pausar()
    return s


# ---- formatação como o TSE ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "parte, total, txt, n9",
    [(0, 100, "0,00", "0"), (100, 100, "100,00", "100"), (1, 3, "33,33", "33.333333333"),
     (2, 3, "66,67", "66.666666667"), (5, 1000, "0,50", "0.500000000"), (1, 8, "12,50", "12.500000000"), (0, 0, "0,00", "0")],
)
def test_pct_no_formato_do_tse(parte, total, txt, n9):
    assert pct(parte, total) == (txt, n9)


def test_pct_arredonda_half_up_e_nao_para_o_par():
    assert pct(1, 8)[0] == "12,50" and pct(5, 80)[0] == "6,25"
    assert pct(1005, 10000)[0] == "10,05"
    assert pct(25, 1000)[0] == "2,50" and pct(125, 10000)[0] == "1,25"
    assert pct(1, 200)[0] == "0,50" and pct(3, 800)[0] == "0,38"  # 0,375 -> 0,38 (half-up; round() daria 0,38 ou 0,37)


def test_repartir_soma_exatamente_o_total():
    for total in (0, 1, 7, 1000, 123456789):
        partes = gerador.repartir(total, [6.0, 5.0, 2.0, 1.2, 0.8, 0.5])
        assert sum(partes) == total and all(x >= 0 for x in partes)


# ---- coerência dos dados ------------------------------------------------------------------------
@pytest.mark.parametrize("x", [0.0, 0.05, 0.3, 0.7, 0.95, 1.0, 1.2])
def test_hierarquia_municipio_uf_brasil_fecha(x):
    sim, passo = sim_em(x), sim_em(x).passo()
    for cargo in (1, 3, 5):
        ufs = (UFS + (EXTERIOR,)) if cargo == 1 else UFS
        for uf in ufs:
            soma = gerador.Agg()
            for k in range(gerador.N_MUNICIPIOS):
                soma.somar(sim.municipio(cargo, uf, k, passo))
            uf_agg = sim.agregado(cargo, uf, None, passo)
            assert (uf_agg.st, uf_agg.est, uf_agg.c, uf_agg.votos) == (soma.st, soma.est, soma.c, soma.votos)
    br = sim.agregado(1, BRASIL, None, passo)
    soma_ufs = sum(sim.agregado(1, uf, None, passo).votos[0] for uf in UFS + (EXTERIOR,))
    assert br.votos[0] == soma_ufs and br.ts == sum(t for t, _ in gerador.TAMANHOS.values())


@pytest.mark.parametrize("x", [0.0, 0.4, 0.8, 1.0])
def test_invariantes_do_ea20_simulado(x):
    sim = sim_em(x)
    for ele, cargo, abr in [(6257, 1, "br"), (6257, 1, "sp"), (6259, 3, "mg"), (6259, 5, "ba"), (6257, 1, "zz")]:
        r = p.parse_resultado(gerador.resultado(sim, ele, cargo, abr))
        v, s, e = r["votos"], r["secoes"], r["eleitorado"]
        assert v["tv"] == v["vb"] + v["vn"] + v["vnt"] + v["van"] + v["vansj"] + v["vv"]  # EA20: tv = vb+vn+vnt+van+vansj+vv
        assert v["vvc"] == v["vv"] == sum(c["votos"] for c in r["candidatos"])
        assert s["ts"] == s["st"] + s["snt"] and e["te"] == e["est"] + e["esnt"] and e["est"] == e["c"] + e["a"]
        assert r["fase"] == "s"  # simulado, sempre
        for c in r["candidatos"]:  # percentual publicado = votos / votos a votáveis concorrentes
            assert c["pct"]["t"] == pct(c["votos"], v["vvc"])[0]
            assert c["pct"]["n"] == pytest.approx(float(pct(c["votos"], v["vvc"])[1]))


def test_estados_no_inicio_no_meio_e_no_fim():
    inicio = p.parse_resultado(gerador.resultado(sim_em(0.0), 6257, 1, "br"))
    assert inicio["estado"]["andamento"] == "n" and inicio["totalizado_em"] is None
    assert inicio["secoes"]["st"] == 0 and all(c["votos"] == 0 for c in inicio["candidatos"])

    meio = p.parse_resultado(gerador.resultado(sim_em(0.5), 6257, 1, "br"))
    assert meio["estado"]["andamento"] == "p" and meio["totalizado_em"] is not None
    assert 0 < meio["secoes"]["st"] < meio["secoes"]["ts"] and not any(c["eleito"] for c in meio["candidatos"])

    fim = p.parse_resultado(gerador.resultado(sim_em(1.0), 6257, 1, "br"))
    assert fim["estado"]["andamento"] == "f" and fim["estado"]["totalizacao_final"] is True
    assert fim["secoes"]["st"] == fim["secoes"]["ts"] and fim["secoes"]["pst"]["t"] == "100,00"
    assert fim["estado"]["sem_eleito"] is False
    destaque = [c for c in fim["candidatos"] if c["eleito"]]
    assert len(destaque) in (1, 2) and {c["situacao"] for c in destaque} <= {"Eleito", "2º turno"}


def test_senador_elege_duas_vagas_no_fim():
    r = p.parse_resultado(gerador.resultado(sim_em(1.0), 6259, 5, "sp"))
    assert r["cargo"]["vagas"] == 2 and [c["eleito"] for c in r["candidatos"]][:3] == [True, True, False]
    assert all(len(c["suplentes"]) == 2 and c["vice"] is None for c in r["candidatos"])


def test_resultado_final_e_deterministico():
    a = gerador.resultado(sim_em(1.0), 6259, 3, "rj")
    b = gerador.resultado(sim_em(1.0), 6259, 3, "rj")
    a.pop("hg"), b.pop("hg"), a.pop("dt"), b.pop("dt"), a.pop("ht"), b.pop("ht")  # horário real de geração
    assert a == b


def test_coerencia_dentro_da_etapa_gera_conteudo_identico():
    sim = Simulacao(duracao_s=1000.0, inicio=0.4)
    sim.pausar()
    a, b = gerador.resultado(sim, 6257, 1, "br"), gerador.resultado(sim, 6257, 1, "br")
    assert a == b  # mesmo ETag enquanto a etapa não muda


def test_dv_nao_liberado_zera_votos_mas_mantem_secoes():
    sim = sim_em(0.6)
    sim.dv_presidente = False
    r = p.parse_resultado(gerador.resultado(sim, 6257, 1, "br"))
    assert r["estado"]["divulga"] is False and r["votos"]["tv"] == 0 and all(c["votos"] == 0 for c in r["candidatos"])
    assert r["secoes"]["st"] > 0 and r["eleitorado"]["c"] > 0
    governador = p.parse_resultado(gerador.resultado(sim, 6259, 3, "sp"))  # a regra vale só para o Presidente
    assert governador["estado"]["divulga"] is True and governador["votos"]["tv"] > 0


def test_municipio_resultado_e_codigos():
    sim = sim_em(1.0)
    cod = Simulacao.codigo_municipio("sp", 2)
    r = p.parse_resultado(gerador.resultado(sim, 6257, 1, "sp", cod))
    assert r["abrangencia"] == {"tipo": "mu", "codigo": f"{cod:05d}"} and r["estado"]["andamento"] == "f"
    with pytest.raises(KeyError):
        gerador.resultado(sim, 6257, 1, "sp", 99999)


def test_mesmas_chaves_dos_arquivos_reais(fixture_json):
    """O simulador precisa ter o mesmo 'formato' do feed real (EA20 e EA14), senão o ensaio engana."""
    real = fixture_json("ele2026/6257/dados/br/br-c0001-e006257-u.json")
    sim = gerador.resultado(sim_em(0.5), 6257, 1, "br")
    assert set(real) <= set(sim)
    for bloco in ("s", "e", "v"):
        assert set(real[bloco]) == set(sim[bloco]), bloco
    assert set(real["carg"][0]) == set(sim["carg"][0])
    assert set(real["carg"][0]["agr"][0]) == set(sim["carg"][0]["agr"][0])
    par_real, par_sim = real["carg"][0]["agr"][0]["par"][0], sim["carg"][0]["agr"][0]["par"][0]
    cand_real, cand_sim = par_real["cand"][0], par_sim["cand"][0]
    # a destinação do voto (`dvt`) só aparece depois da primeira totalização; o resto é idêntico
    assert set(par_sim) - set(par_real) == {"dvt"} and set(par_real) <= set(par_sim)
    assert set(cand_sim) - set(cand_real) == {"dvt"} and set(cand_real) <= set(cand_sim)
    pre = gerador.resultado(sim_em(0.0), 6257, 1, "br")  # antes de totalizar, a estrutura é exatamente a real
    assert set(pre["carg"][0]["agr"][0]["par"][0]) == set(par_real)
    assert set(pre["carg"][0]["agr"][0]["par"][0]["cand"][0]) == set(cand_real)

    ab_real = fixture_json("ele2026/6257/dados/br/br-e006257-ab.json")
    ab_sim = gerador.acompanhamento(sim_em(0.5), 6257)
    assert set(ab_real) == set(ab_sim) and len(ab_real["abr"]) == len(ab_sim["abr"]) == 29
    br_real, br_sim = ab_real["abr"][0 if ab_real["abr"][0]["tpabr"] == "br" else 1], ab_sim["abr"][0]
    assert set(br_real["s"]) == set(br_sim["s"]) and set(br_real["e"]) == set(br_sim["e"])
    uf_real = next(a for a in ab_real["abr"] if a["tpabr"] == "uf")
    uf_sim = next(a for a in ab_sim["abr"] if a["tpabr"] == "uf")
    assert set(uf_real) == set(uf_sim)


def test_acompanhamento_conta_ufs_e_municipios():
    ab = p.parse_acompanhamento(gerador.acompanhamento(sim_em(0.0), 6257))
    br = next(a for a in ab["abrangencias"] if a["tipo"] == "br")
    assert br["andamento"] == "n" and br["contagem"]["ufsnr"] == 28
    ab = p.parse_acompanhamento(gerador.acompanhamento(sim_em(1.0), 6257))
    br = next(a for a in ab["abrangencias"] if a["tipo"] == "br")
    assert br["andamento"] == "f" and br["contagem"]["ufsf"] == 28 and br["secoes"]["st"] == br["secoes"]["ts"]
    uf = p.parse_acompanhamento(gerador.acompanhamento(sim_em(0.5), 6257, "sp"))
    assert [a["tipo"] for a in uf["abrangencias"]] == ["uf"] + ["mun"] * gerador.N_MUNICIPIOS


# ---- servidor ------------------------------------------------------------------------------------
@pytest.fixture
def cliente_http():
    app = criar_app(sim_em(0.5))
    return app.test_client(), app.config["SIM"]


def test_servidor_serve_etag_e_304(cliente_http):
    http, _ = cliente_http
    r = http.get("/simulado/ele2026/6257/dados/br/br-c0001-e006257-u.json")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "max-age=8" and r.headers["ETag"]
    r2 = http.get("/simulado/ele2026/6257/dados/br/br-c0001-e006257-u.json", headers={"If-None-Match": r.headers["ETag"]})
    assert r2.status_code == 304 and r2.data == b""


@pytest.mark.parametrize(
    "caminho",
    [
        "/simulado/ele2026/6257/dados/br/br-c0003-e006257-u.json",  # Governador não é da eleição 6257
        "/simulado/ele2026/6259/dados/br/br-c0003-e006259-u.json",  # Governador não tem arquivo BR
        "/simulado/ele2026/6259/dados/zz/zz-c0003-e006259-u.json",  # exterior só vota Presidente
        "/simulado/ele2026/6257/dados/sp/mg-c0001-e006257-u.json",  # UF do arquivo diferente da pasta
        "/simulado/ele2026/6257/dados/sp/sp99999-c0001-e006257-u.json",  # município inexistente
        "/simulado/ele2026/6257/dados/xx/xx-c0001-e006257-u.json",
        "/simulado/ele2026/6261/config/mun-e006261-cm.json",
    ],
)
def test_servidor_responde_404_para_o_que_nao_existe(cliente_http, caminho):
    assert cliente_http[0].get(caminho).status_code == 404


def test_servidor_injeta_falhas_e_controla_a_simulacao(cliente_http):
    http, sim = cliente_http
    url = "/simulado/comum/config/ele-c.json"
    assert http.get(url).status_code == 200
    assert http.get("/__sim/falha/503/30").status_code == 200  # o controle nunca é afetado pela falha
    assert http.get(url).status_code == 503
    assert http.get("/__sim/falha/limpar").status_code == 200 and http.get(url).status_code == 200
    assert http.get("/__sim/ir/100").get_json()["x"] == pytest.approx(1.0, abs=0.01)
    assert http.get("/__sim/dv/n").get_json()["dv_presidente"] is False
    assert http.get("/__sim/velocidade/4").get_json()["velocidade"] == 4.0


def test_foto_do_simulador_e_um_jpeg_valido(cliente_http):
    r = cliente_http[0].get("/simulado/ele2026/6257/fotos/br/900001000001.jpeg")
    assert r.status_code == 200 and r.data[:2] == b"\xff\xd8" and r.data[-2:] == b"\xff\xd9"


# ---- integração: cliente HTTP real + poller real contra o simulador local ------------------------
def test_poller_real_contra_o_simulador_nao_gera_404_e_preenche_tudo():
    sim = Simulacao(duracao_s=100000.0, inicio=0.5)  # progresso ~0,5 e quase parado durante o teste
    sim.pausar()
    servidor = make_server("127.0.0.1", 0, criar_app(sim), threaded=True)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    cfg = Settings(
        tse_base=f"http://127.0.0.1:{servidor.server_port}", ambiente="simulado", escala_polling=0.01,
        max_rps=200, workers=6, iniciar_poller=False,
    )
    cliente = TseClient(user_agent="teste", max_rps=cfg.max_rps, workers=cfg.workers)
    store = Store()
    poller = Poller(cfg, cliente, store)
    try:
        poller.iniciar()
        limite = time.monotonic() + 20
        while time.monotonic() < limite:
            estado = poller.estado()
            if estado["alvos"] >= 88 and len(store.itens()) >= 88:
                break
            time.sleep(0.2)
        estado = poller.estado()
        assert estado["alvos"] == 88  # EA11 + 2 EA12 + 2 EA14 + 83 EA20 (Presidente BR/UF, Governador, Senador)
        assert len(store.itens()) == 88, estado["com_problema"][:5]
        assert estado["total_com_problema"] == 0 and estado["cliente"]["por_status"].get("404") is None
        assert estado["cliente"]["disjuntor"]["aberto"] is False

        br = store.get("u:6257:1:br").dados
        assert br["fase"] == "s" and br["estado"]["andamento"] == "p" and len(br["candidatos"]) == 6
        soma = sum(store.get(f"u:6257:1:{uf}").dados["votos"]["vv"] for uf in UFS + (EXTERIOR,))
        assert soma == br["votos"]["vv"]  # os 28 arquivos de UF fecham com o arquivo do Brasil
        assert store.get("cm:6257").dados["ufs"]["sp"]["municipios"][0]["capital"] is True
        assert store.get("ab:6257:br").dados["abrangencias"][0]["tipo"] == "br"
    finally:
        poller.parar()
        servidor.shutdown()
