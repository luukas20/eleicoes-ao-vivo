"""API JSON, páginas e rota de fotos, com o app alimentado pelo simulador (sem rede)."""
import pytest

from tests.conftest import popular_store

SQ_PRESIDENTE_0 = "9000010000"  # candidato fictício do simulador (Presidente, 1º da lista)


def json_de(resposta):
    assert resposta.status_code == 200, resposta.data[:300]
    return resposta.get_json()


# ---- meta ---------------------------------------------------------------------------------------------
def test_meta(novo_app):
    app, _, _ = novo_app(0.5)
    m = json_de(app.test_client().get("/api/v1/meta"))
    assert m["fase"] == "s" and m["data"] == "2026-10-04" and m["turnos"] == [1] and m["turno_padrao"] == 1
    assert [c["slug"] for c in m["cargos"]] == ["presidente", "governador", "senador"]
    assert len(m["ufs"]) == 27 and m["frescor"]["desatualizado"] is False and m["frescor"]["defasagem_s"] < 5


def test_sem_dados_ainda_a_api_responde_404_amigavel_e_frescor_aguardando(tmp_path):
    from app import create_app
    from app.config import Settings

    app = create_app(Settings(data_dir=tmp_path, iniciar_poller=False), iniciar_poller=False)
    c = app.test_client()
    r = c.get("/api/v1/presidente")
    assert r.status_code == 404 and "erro" in r.get_json()
    assert r.headers["X-Desatualizado"] == "1" and r.headers["X-Defasagem-S"] == ""
    assert c.get("/api/v1/meta").get_json()["frescor"]["aguardando_primeiro_contato"] is True


# ---- Presidente ---------------------------------------------------------------------------------------
def test_presidente_antes_da_apuracao(novo_app):
    app, _, _ = novo_app(0.0)
    d = json_de(app.test_client().get("/api/v1/presidente"))
    r = d["resultado"]
    assert d["disponivel"] and r["estado"]["andamento"] == "n" and r["secoes"]["st"] == 0
    assert len(r["candidatos"]) == 6 and all(c["votos"] == 0 and c["cor"] == 0 for c in r["candidatos"])
    assert d["legenda"] == [] and len(d["ufs"]) == 28
    assert all(u["disponivel"] and u["top"] == [] and u["margem_pp"] is None for u in d["ufs"])


def test_presidente_no_meio_da_apuracao(novo_app):
    app, _, _ = novo_app(0.5)
    d = json_de(app.test_client().get("/api/v1/presidente"))
    r = d["resultado"]
    assert r["estado"]["andamento"] == "p" and 0 < r["secoes"]["st"] < r["secoes"]["ts"]
    assert [c["cor"] for c in d["legenda"]] == [1, 2, 3]  # três primeiros colocados ganham as cores 1..3
    lideres = [c for c in r["candidatos"] if c["cor"] > 0]
    assert len(lideres) == 3 and r["candidatos"][0]["cor"] == 1  # ordenado por votos; 1º recebeu o slot 1
    assert all(c["foto"] == f"/foto/6257/br/{c['sq']}" for c in r["candidatos"])
    assert "obtido_em" not in str(d)  # nada volátil no corpo: o ETag precisa ficar estável
    sp = next(u for u in d["ufs"] if u["codigo"] == "sp")
    assert sp["top"][0]["votos"] >= sp["top"][1]["votos"] and sp["margem_pp"] >= 0
    assert d["ufs_andamento"]["ufsnr"] + d["ufs_andamento"]["ufspt"] + d["ufs_andamento"]["ufsf"] == 28


def test_a_cor_segue_o_candidato_e_nao_a_posicao(novo_app):
    app, store, _ = novo_app(0.3)
    c = app.test_client()
    antes = {x["sq"]: x["cor"] for x in json_de(c.get("/api/v1/presidente"))["resultado"]["candidatos"] if x["cor"]}
    assert len(antes) == 3
    popular_store(store, 1.0)  # fim da apuração: o ranking pode mudar, as cores já atribuídas não
    depois = {x["sq"]: x["cor"] for x in json_de(c.get("/api/v1/presidente"))["resultado"]["candidatos"] if x["cor"]}
    assert all(depois[sq] == cor for sq, cor in antes.items())


def test_cores_nao_sao_atribuidas_no_comecinho_da_apuracao(novo_app):
    app, _, _ = novo_app(0.01)  # menos de 1% das seções totalizadas: ranking ainda instável
    r = json_de(app.test_client().get("/api/v1/presidente"))["resultado"]
    assert all(c["cor"] == 0 for c in r["candidatos"])


def test_etag_estavel_entre_consultas_e_304(novo_app):
    app, store, _ = novo_app(0.5)
    c = app.test_client()
    r1 = c.get("/api/v1/presidente")
    tag = r1.headers["ETag"]
    r2 = c.get("/api/v1/presidente", headers={"If-None-Match": tag})
    assert r2.status_code == 304 and r2.data == b""
    assert r2.headers["X-Defasagem-S"] and r2.headers["X-Desatualizado"] == "0"  # frescor chega até no 304
    store.confirmar("u:6257:1:br")  # o TSE só confirmou que nada mudou: o corpo (e o ETag) não muda
    assert c.get("/api/v1/presidente").headers["ETag"] == tag
    popular_store(store, 0.9)  # dados novos => ETag novo
    assert c.get("/api/v1/presidente").headers["ETag"] != tag


def test_votacao_nao_liberada_aparece_no_estado(novo_app):
    from mock import gerador
    from mock.gerador import Simulacao
    from app.tse import parse

    app, store, _ = novo_app(0.6)
    sim = Simulacao(duracao_s=100.0, inicio=0.6)
    sim.pausar()
    sim.dv_presidente = False
    dados = parse.parse_resultado(gerador.resultado(sim, 6257, 1, "br"))
    store.guardar("u:6257:1:br", "u", dados, idg="nova", etag=None, url="x")
    r = json_de(app.test_client().get("/api/v1/presidente"))["resultado"]
    assert r["estado"]["divulga"] is False and r["votos"]["tv"] == 0 and r["secoes"]["st"] > 0


# ---- demais cargos ------------------------------------------------------------------------------------
def test_tabela_de_governadores(novo_app):
    app, _, _ = novo_app(0.6)
    d = json_de(app.test_client().get("/api/v1/cargo/governador"))
    assert d["slug"] == "governador" and d["vagas"] == 1 and len(d["linhas"]) == 27
    linha = next(l for l in d["linhas"] if l["codigo"] == "mg")
    assert len(linha["top"]) == 2 and linha["top"][0]["votos"] >= linha["top"][1]["votos"]


def test_tabela_de_senadores_mostra_duas_vagas_e_o_terceiro(novo_app):
    app, _, _ = novo_app(0.6)
    d = json_de(app.test_client().get("/api/v1/cargo/senador"))
    assert d["vagas"] == 2 and len(d["linhas"]) == 27
    assert all(len(l["top"]) == 3 for l in d["linhas"] if l["secoes"]["st"] > 0)  # 2 vagas + o primeiro fora


def test_diferenca_mede_a_distancia_para_fora_das_vagas(novo_app):
    app, _, _ = novo_app(0.6)
    c = app.test_client()
    mg_sen = next(l for l in json_de(c.get("/api/v1/cargo/senador"))["linhas"] if l["codigo"] == "mg")
    assert mg_sen["margem_pp"] == pytest.approx(mg_sen["top"][1]["pct"]["n"] - mg_sen["top"][2]["pct"]["n"], abs=0.006)  # 2º x 3º
    mg_gov = next(l for l in json_de(c.get("/api/v1/cargo/governador"))["linhas"] if l["codigo"] == "mg")
    assert mg_gov["margem_pp"] == pytest.approx(mg_gov["top"][0]["pct"]["n"] - mg_gov["top"][1]["pct"]["n"], abs=0.006)  # 1º x 2º
    assert mg_gov["totalizado_em"] and mg_gov["secoes"]["pst"]["n"] > 0


def test_pagina_da_uf_traz_as_tres_disputas(novo_app):
    app, _, _ = novo_app(0.7)
    d = json_de(app.test_client().get("/api/v1/uf/sp"))
    assert d["uf"] == "sp" and d["nome"] == "São Paulo"
    assert [x["slug"] for x in d["disputas"]] == ["presidente", "governador", "senador"]
    gov = next(x for x in d["disputas"] if x["slug"] == "governador")["resultado"]
    assert gov["abrangencia"]["codigo"] == "sp" and len(gov["candidatos"]) == 4
    assert all(c["foto"].startswith("/foto/6259/sp/") for c in gov["candidatos"])  # foto do governador: pasta da UF
    pres = next(x for x in d["disputas"] if x["slug"] == "presidente")["resultado"]
    assert all(c["foto"].startswith("/foto/6257/br/") for c in pres["candidatos"])  # foto do presidente: pasta br


def test_final_da_apuracao_marca_eleitos_e_segundo_turno(novo_app):
    app, _, _ = novo_app(1.0)
    d = json_de(app.test_client().get("/api/v1/presidente"))
    r = d["resultado"]
    assert r["estado"]["totalizacao_final"] and r["secoes"]["st"] == r["secoes"]["ts"]
    marcados = [c for c in r["candidatos"] if c["eleito"]]
    assert len(marcados) in (1, 2) and {c["situacao"] for c in marcados} <= {"Eleito", "2º turno"}
    sen = json_de(app.test_client().get("/api/v1/uf/ba"))["disputas"][2]["resultado"]
    assert [c["eleito"] for c in sen["candidatos"]][:3] == [True, True, False]


# ---- municípios ---------------------------------------------------------------------------------------
def test_busca_de_municipios_ignora_acentos_e_prioriza_o_inicio_do_nome(novo_app):
    app, _, _ = novo_app(0.5)
    c = app.test_client()
    r = json_de(c.get("/api/v1/municipios?uf=sp&q=sao%20pa"))
    assert r["resultados"][0]["nome"].startswith("SÃO PAULO") and r["resultados"][0]["capital"] is True
    assert json_de(c.get("/api/v1/municipios?uf=sp&q=SAO%20PAULO"))["resultados"][0]["cd"] == r["resultados"][0]["cd"]  # caixa e acento
    meio = json_de(c.get("/api/v1/municipios?uf=sp&q=simulado%202"))["resultados"]
    assert len(meio) == 1 and "SIMULADO 2" in meio[0]["nome"]  # também acha no meio do nome
    capital = json_de(c.get("/api/v1/municipios?uf=mg&q="))["resultados"]  # sem termo: sugere a capital
    assert len(capital) == 1 and capital[0]["capital"] is True
    assert json_de(c.get("/api/v1/municipios?uf=sp&q=xyzxyz"))["resultados"] == []


@pytest.mark.parametrize("consulta, status", [
    ("uf=xx&q=a", 404), ("uf=zz&q=a", 404), ("uf=&q=a", 404), ("uf=sp&q=" + "a" * 61, 400),
])
def test_busca_de_municipios_valida_a_entrada(novo_app, consulta, status):
    app, _, _ = novo_app(0.5)
    assert app.test_client().get(f"/api/v1/municipios?{consulta}").status_code == status


def test_busca_sem_a_lista_do_tse_ainda_carregada_responde_503(tmp_path):
    from app import create_app
    from app.config import Settings

    c = create_app(Settings(data_dir=tmp_path, iniciar_poller=False), iniciar_poller=False).test_client()
    r = c.get("/api/v1/municipios?uf=sp&q=sao")
    assert r.status_code == 503 and r.headers["Retry-After"] == "5"


def test_pagina_do_municipio_pede_o_acompanhamento_e_so_aceita_codigos_do_ea12(novo_app):
    from mock.gerador import Simulacao

    app, store, _ = novo_app(0.6)
    poller = app.extensions["poller"]
    c = app.test_client()
    codigo = f"{Simulacao.codigo_municipio('sp', 2):05d}"
    d = json_de(c.get(f"/api/v1/municipio/sp/{codigo}"))
    assert d["municipio"]["nome"] == "SÃO PAULO - MUNICIPIO SIMULADO 2" and d["municipio"]["capital"] is False and d["uf"] == "sp"
    assert [x["slug"] for x in d["disputas"]] == ["presidente", "governador", "senador"]
    assert not any(x["disponivel"] for x in d["disputas"])  # ainda não chegou nada: o poller acaba de ser acionado
    pedidos = sorted(k for k, e in poller._estados.items() if e.expira_em is not None)
    assert pedidos == [f"u:6257:1:sp:{int(codigo)}", f"u:6259:3:sp:{int(codigo)}", f"u:6259:5:sp:{int(codigo)}"]
    assert all(poller._estados[k].alvo.camada == "sob_demanda" for k in pedidos)

    # simula a chegada dos arquivos do município e confere o resultado e as cores (as do escopo da UF)
    from app.tse import parse
    from mock import gerador

    sim = Simulacao(duracao_s=100.0, inicio=0.6)
    sim.pausar()
    for ele, cargo in ((6257, 1), (6259, 3), (6259, 5)):
        dados = parse.parse_resultado(gerador.resultado(sim, ele, cargo, "sp", int(codigo)))
        store.guardar(f"u:{ele}:{cargo}:sp:{int(codigo)}", "u", dados, idg=dados["idg"], etag=None, url="x")
    d = json_de(c.get(f"/api/v1/municipio/sp/{codigo}"))
    assert all(x["disponivel"] for x in d["disputas"])
    pres = d["disputas"][0]["resultado"]
    assert pres["abrangencia"] == {"tipo": "mu", "codigo": codigo, "nome": "SÃO PAULO - MUNICIPIO SIMULADO 2"}
    assert [x["cor"] for x in pres["candidatos"] if x["cor"]] and all(x["foto"].startswith("/foto/6257/br/") for x in pres["candidatos"])
    assert d["disputas"][1]["resultado"]["candidatos"][0]["foto"].startswith("/foto/6259/sp/")


@pytest.mark.parametrize("caminho", [
    "/api/v1/municipio/sp/99999",  # não está no EA12: nunca montamos essa URL (evita 404 em massa no TSE)
    "/api/v1/municipio/sp/abc", "/api/v1/municipio/xx/10000", "/api/v1/municipio/zz/10000", "/api/v1/municipio/sp/..%2f10000",
])
def test_municipio_inexistente_nao_gera_alvo_no_poller(novo_app, caminho):
    app, _, _ = novo_app(0.5)
    r = app.test_client().get(caminho)
    assert r.status_code == 404
    assert not [k for k, e in app.extensions["poller"]._estados.items() if e.expira_em is not None]


def test_limite_de_municipios_acompanhados_ao_mesmo_tempo(novo_app, tmp_path):
    from app import create_app
    from app.config import Settings
    from app.store import Store
    from app.tse.client import TokenBucket, TseClient
    from mock.gerador import Simulacao
    from tests.conftest import SessaoTSE

    store = Store()
    cliente = TseClient(user_agent="t", session=SessaoTSE(), bucket=TokenBucket(1000))
    app = create_app(Settings(data_dir=tmp_path, iniciar_poller=False, max_sob_demanda=3), store=store, client=cliente, iniciar_poller=False)
    popular_store(store, 0.5)
    c = app.test_client()
    # três alvos por município: o 1º município enche o limite de 3; o 2º não consegue entrar
    assert c.get(f"/api/v1/municipio/sp/{Simulacao.codigo_municipio('sp', 0):05d}").status_code == 200
    r = c.get(f"/api/v1/municipio/rj/{Simulacao.codigo_municipio('rj', 0):05d}")
    assert r.status_code == 503 and "muitos municípios" in r.get_json()["erro"]
    assert c.get(f"/api/v1/municipio/sp/{Simulacao.codigo_municipio('sp', 0):05d}").status_code == 200  # o já acompanhado segue


def test_paginas_de_municipio_html(novo_app):
    app, _, _ = novo_app(0.5)
    c = app.test_client()
    r = c.get("/municipio/sp/10300")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'data-codigo="10300"' in html and 'data-uf="sp"' in html
    assert 'id="busca-mun"' in c.get("/uf/sp").get_data(as_text=True)
    assert c.get("/municipio/sp/abc").status_code == 404 and c.get("/municipio/zz/00001").status_code == 404
    assert 'data-codigo="00042"' in c.get("/municipio/sp/42").get_data(as_text=True)  # completa com zeros


# ---- erros e segurança --------------------------------------------------------------------------------
@pytest.mark.parametrize("caminho, status", [
    ("/api/v1/uf/xx", 404), ("/api/v1/uf/zz", 404), ("/api/v1/cargo/prefeito", 404), ("/api/v1/cargo/presidente", 404),
    ("/api/v1/presidente?turno=3", 400), ("/api/v1/presidente?turno=abc", 400), ("/api/v1/presidente?turno=2", 404),
])
def test_erros(novo_app, caminho, status):
    app, _, _ = novo_app(0.5)
    r = app.test_client().get(caminho)
    assert r.status_code == status and "erro" in r.get_json()


def test_cabecalhos_de_seguranca(novo_app):
    app, _, _ = novo_app(0.5)
    r = app.test_client().get("/")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"] and "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert "unsafe-inline" not in r.headers["Content-Security-Policy"] and "unsafe-eval" not in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["Referrer-Policy"] == "no-referrer"


def test_status_da_api(novo_app):
    app, _, _ = novo_app(0.5)
    d = json_de(app.test_client().get("/api/v1/status"))
    assert d["armazenamento"]["arquivos"] == 88 and d["poller"]["rodando"] is False
    assert d["poller"]["cliente"]["disjuntor"]["aberto"] is False
    assert {e["cargo"] for e in d["eleicoes"]} == {"presidente", "governador", "senador"}


# ---- páginas e estáticos ------------------------------------------------------------------------------
@pytest.mark.parametrize("caminho, trecho", [
    ("/", 'data-pagina="painel"'), ("/uf/sp", 'data-uf="sp"'), ("/governadores", 'data-slug="governador"'),
    ("/senadores", 'data-slug="senador"'), ("/status", 'id="conteudo-status"'),
])
def test_paginas_html(novo_app, caminho, trecho):
    app, _, _ = novo_app(0.5)
    r = app.test_client().get(caminho)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and trecho in html and 'lang="pt-BR"' in html and "não oficial" in html
    assert "<script>" not in html and ' style="' not in html  # nada inline: a CSP bloquearia


def test_pagina_de_uf_invalida_e_404(novo_app):
    app, _, _ = novo_app(0.5)
    c = app.test_client()
    assert c.get("/uf/zz").status_code == 404 and c.get("/uf/xx").status_code == 404 and c.get("/uf/SP").status_code == 200


def test_navegacao_marca_a_aba_ativa(novo_app):
    app, _, _ = novo_app(0.5)
    assert 'href="/governadores" aria-current="page"' in app.test_client().get("/governadores").get_data(as_text=True)
    assert 'href="/" aria-current="page"' in app.test_client().get("/").get_data(as_text=True)


@pytest.mark.parametrize("arquivo, tipo", [
    ("css/app.css", "text/css"), ("js/painel.js", "javascript"), ("js/componentes.js", "javascript"), ("img/favicon.svg", "image/svg+xml"),
])
def test_estaticos(novo_app, arquivo, tipo):
    app, _, _ = novo_app(0.5)
    r = app.test_client().get(f"/static/{arquivo}")
    assert r.status_code == 200 and tipo in r.headers["Content-Type"]


# ---- fotos ----------------------------------------------------------------------------------------------
def test_foto_busca_no_tse_uma_vez_e_depois_serve_do_disco(novo_app, tmp_path):
    app, _, sessao = novo_app(0.5)
    c = app.test_client()
    r1 = c.get(f"/foto/6257/br/{SQ_PRESIDENTE_0}")
    assert r1.status_code == 200 and r1.mimetype == "image/jpeg" and r1.data[:2] == b"\xff\xd8"
    assert "max-age=86400" in r1.headers["Cache-Control"]
    assert (tmp_path / "fotos" / "6257" / "br" / f"{SQ_PRESIDENTE_0}.jpeg").exists()
    chamadas = len(sessao.chamadas)
    assert chamadas == 1 and sessao.chamadas[0].endswith(f"/ele2026/6257/fotos/br/{SQ_PRESIDENTE_0}.jpeg")
    assert c.get(f"/foto/6257/br/{SQ_PRESIDENTE_0}").data == r1.data and len(sessao.chamadas) == chamadas  # do disco


def test_foto_de_candidato_desconhecido_nao_gera_requisicao_ao_tse(novo_app):
    app, _, sessao = novo_app(0.5)
    r = app.test_client().get("/foto/6257/br/123456789012")
    assert r.status_code == 200 and r.mimetype == "image/svg+xml" and sessao.chamadas == []


@pytest.mark.parametrize("caminho", ["/foto/6257/xx/1", "/foto/6257/br/abc", "/foto/6257/br/" + "9" * 30, "/foto/6257/../etc/1"])
def test_foto_com_parametro_invalido_e_404(novo_app, caminho):
    app, _, sessao = novo_app(0.5)
    assert app.test_client().get(caminho).status_code == 404 and sessao.chamadas == []


def test_foto_inexistente_no_tse_vira_placeholder_com_cache_negativo(novo_app):
    app, _, sessao = novo_app(0.5)
    sessao.fotos_inexistentes.add(SQ_PRESIDENTE_0)
    c = app.test_client()
    r = c.get(f"/foto/6257/br/{SQ_PRESIDENTE_0}")
    assert r.mimetype == "image/svg+xml" and len(sessao.chamadas) == 1
    c.get(f"/foto/6257/br/{SQ_PRESIDENTE_0}")
    assert len(sessao.chamadas) == 1  # lembrou do 404: não pergunta de novo (404 repetido pode bloquear o IP)
