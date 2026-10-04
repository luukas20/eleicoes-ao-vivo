"""Deputados Federal, Estadual e Distrital: arquivo real do DF, agrupamentos, vagas, busca e API (sem rede)."""
from collections import Counter

import pytest

from app import partidos
from app.tse import parse
from tests.conftest import montar_app

CORES_VALIDAS = set(partidos.todas_as_chaves())


def json_de(resposta):
    assert resposta.status_code == 200, resposta.data[:300]
    return resposta.get_json()


@pytest.fixture(scope="module")
def meio(tmp_path_factory):
    """App com o simulador em ~50% da apuração (vagas provisórias, ninguém marcado como eleito)."""
    app, store, _ = montar_app(tmp_path_factory.mktemp("meio"), 0.5)
    return app.test_client()


@pytest.fixture(scope="module")
def fim(tmp_path_factory):
    """App com o simulador no fim: totalização final, TSE já marcou os eleitos."""
    app, store, _ = montar_app(tmp_path_factory.mktemp("fim"), 1.0)
    return app.test_client()


# ---- cores dos agrupamentos ---------------------------------------------------------------------------
def test_partido_representante_da_federacao_e_o_de_maior_prioridade():
    assert partidos.partido_representante("PCDOB / PT / PV") == "PT"
    assert partidos.partido_representante("PT/PC do B/PV") == "PT"
    assert partidos.partido_representante("CIDADANIA / PSDB") == "PSDB"
    assert partidos.partido_representante("PP / UNIÃO") == "UNIÃO"
    assert partidos.partido_representante("PSOL/REDE") == "PSOL"
    assert partidos.partido_representante("XPTO / ZZZ") is None and partidos.partido_representante("") is None


def test_cor_do_agrupamento_e_estavel_e_valida():
    assert partidos.chave_do_agrupamento("PL", "PL") == partidos.chave_do_partido("PL") == "pl"
    assert partidos.chave_do_agrupamento("CIDADANIA / PSDB") == partidos.chave_do_partido("PSDB")
    assert partidos.chave_do_agrupamento("PSOL/REDE") == "psol"
    assert partidos.chave_do_agrupamento("XPTO", "XPTO") in partidos.RESERVA  # sigla que o painel não conhece: reserva fixa
    assert partidos.chave_do_agrupamento("XPTO", "XPTO") == partidos.chave_do_agrupamento("XPTO", "XPTO")
    assert partidos.chave_do_agrupamento("") == "neutro"


# ---- arquivo real: Deputado Distrital do DF, antes de a apuração começar -------------------------------
@pytest.fixture(scope="module")
def distrital_df(fixture_json):
    return parse.parse_resultado(fixture_json("ele2026/6259/dados/df/df-c0008-e006259-u.json"))


def test_distrital_real_do_df_antes_da_apuracao(distrital_df):
    r = distrital_df
    assert r["cargo"]["cd"] == 8 and r["cargo"]["vagas"] == 24 and r["cargo"]["quociente_eleitoral"] == 0
    assert r["abrangencia"] == {"tipo": "uf", "codigo": "df"}
    assert r["estado"]["andamento"] == "n" and r["estado"]["totalizacao_final"] is False
    assert len(r["candidatos"]) == 415 and len(r["agremiacoes"]) == 19
    assert all(c["votos"] == 0 and not c["eleito"] and not c["situacao"] for c in r["candidatos"])  # nada de eleito sem totalização


def test_distrital_real_candidatos_apontam_para_agremiacoes_que_existem(distrital_df):
    r = distrital_df
    por_agr = Counter(c["agr"] for c in r["candidatos"])
    assert set(por_agr) <= {a["n"] for a in r["agremiacoes"]}
    for a in r["agremiacoes"]:
        assert por_agr[a["n"]] == sum(p["candidatos"] for p in a["partidos"]), a["nome"]  # o EA20 declara quantos candidatos tem cada partido
        assert a["tipo"] in ("i", "f") and bool(a["partidos"])
    assert all(c["agremiacao_tipo"] in ("i", "f") and c["composicao"] for c in r["candidatos"])


def test_distrital_real_federacoes_tem_partidos_marcados(distrital_df):
    federacoes = [a for a in distrital_df["agremiacoes"] if a["tipo"] == "f"]
    assert {a["composicao"] for a in federacoes} >= {"PCDOB / PT / PV", "CIDADANIA / PSDB"}
    assert all(len(a["partidos"]) >= 2 and all(p["federacao"] for p in a["partidos"]) for a in federacoes)
    isolados = [a for a in distrital_df["agremiacoes"] if a["tipo"] == "i"]
    assert isolados and all(len(a["partidos"]) == 1 and not a["partidos"][0]["federacao"] for a in isolados)


def test_servico_com_o_arquivo_real_sem_votos_nao_inventa_vagas_nem_eleitos(tmp_path, fixture_json):
    """O formato real, com tudo zerado: nada de destaque, vaga ou eleito, e nenhum percentual calculado sobre zero."""
    from app.config import Settings
    from app.servico import Servico
    from app.store import Store

    store = Store()
    cfg = parse.parse_config_eleicoes(fixture_json("comum/config/ele-c.json"))
    store.guardar("cfg", "cfg", cfg, idg=cfg["idg"], etag=None, url="cfg")
    r = parse.parse_resultado(fixture_json("ele2026/6259/dados/df/df-c0008-e006259-u.json"))
    store.guardar("u:6259:8:df", "u", r, idg=r["idg"], etag=None, url="u")
    sv = Servico(Settings(data_dir=tmp_path, iniciar_poller=False), store)

    p = sv.painel_proporcional("deputado-distrital", "df")
    assert p["disponivel"] and p["total_candidatos"] == 415 and p["vagas_distribuidas"] == 0
    assert p["destaques"] == [] and p["eleitos"] == []
    assert len(p["agrupamentos"]) == 19 and all(g["pct_validos"] is None and g["vagas"] == 0 for g in p["agrupamentos"])
    fe_brasil = next(g for g in p["agrupamentos"] if g["composicao"] == "PCDOB/PT/PV")
    assert fe_brasil["tipo"] == "f" and fe_brasil["chave"] == "f:101" and fe_brasil["cor_partido"] == "pt"  # a federação usa a cor do PT
    cores = [g["cor"] for g in p["agrupamentos"]]
    assert len(set(cores)) == len(cores) and set(cores) <= CORES_VALIDAS  # dentro da UF, nenhum agrupamento repete a cor de outro
    assert fe_brasil["candidatos"] == 24 and {x["sigla"] for x in fe_brasil["partidos"]} == {"PT", "PCDOB", "PV"}
    assert fe_brasil["mais_votado"] is None
    assert sv.painel_proporcional("deputado-distrital", "sp") is None and sv.painel_proporcional("deputado-estadual", "df") is None


# ---- o simulador gera deputados com a mesma estrutura do arquivo real ------------------------------------
def test_simulador_de_deputados_tem_as_chaves_do_arquivo_real(fixture_json):
    from mock import gerador
    from mock.gerador import Simulacao

    real = fixture_json("ele2026/6259/dados/df/df-c0008-e006259-u.json")
    sim = Simulacao(duracao_s=100.0, inicio=1.0)
    sim.pausar()
    falso = gerador.resultado(sim, 6259, 8, "df")
    falso = parse.decodificar(falso) if isinstance(falso, (bytes, bytearray)) else falso
    assert set(real) <= set(falso) and set(falso) - set(real) <= {"mnae", "esae"}  # campos que o TSE só traz com a apuração em curso
    rc, fc = real["carg"][0], falso["carg"][0]
    assert set(fc) == set(rc)
    for campo in ("fed", "agr"):
        assert set(fc[campo][0]) == set(rc[campo][0]), campo
    assert set(fc["agr"][0]["par"][0]) == set(rc["agr"][0]["par"][0])
    assert set(rc["agr"][0]["par"][0]["cand"][0]) <= set(fc["agr"][0]["par"][0]["cand"][0])  # o simulador só acrescenta (dvt)


# ---- API: painel por UF -----------------------------------------------------------------------------
def test_painel_da_uf_no_meio_da_apuracao(meio):
    d = json_de(meio.get("/api/v1/proporcional/deputado-federal/sp"))
    assert d["slug"] == "deputado-federal" and d["uf"] == "sp" and d["disponivel"] is True
    cargo = d["resultado"]["cargo"]
    assert cargo["vagas"] == 70 and cargo["quociente_eleitoral"] > 0
    grupos = d["agrupamentos"]
    assert sum(g["vagas"] for g in grupos) == d["vagas_distribuidas"] == 70  # provisórias, mas distribuem todas as vagas
    assert [g["votos_total"] for g in grupos] == sorted((g["votos_total"] for g in grupos), reverse=True)
    assert all(g["cor"] in CORES_VALIDAS for g in grupos)
    assert all(g["votos_total"] == g["votos_nominais"] + g["votos_legenda"] for g in grupos)
    assert all(g["tipo"] in ("i", "f") and g["chave"].split(":")[0] in ("p", "f") for g in grupos)
    assert d["eleitos"] == [] and d["resultado"]["estado"]["totalizacao_final"] is False  # "eleito" só quando o TSE marca
    destaques = d["destaques"]
    assert 0 < len(destaques) <= 20 and [c["votos"] for c in destaques] == sorted((c["votos"] for c in destaques), reverse=True)
    assert [c["posicao"] for c in destaques] == list(range(1, len(destaques) + 1))
    assert all(c["foto"].startswith("/foto/6259/sp/") and c["cor"] in CORES_VALIDAS and not c["eleito"] for c in destaques)


def test_painel_da_uf_no_fim_marca_os_eleitos_pelo_tse(fim):
    d = json_de(fim.get("/api/v1/proporcional/deputado-federal/sp"))
    assert d["resultado"]["estado"]["totalizacao_final"] is True
    assert len(d["eleitos"]) == 70 and all(c["eleito"] for c in d["eleitos"])
    assert sum(g["eleitos"] for g in d["agrupamentos"]) == 70
    assert sum(g["vagas"] for g in d["agrupamentos"]) == 70  # na totalização final as vagas dos agrupamentos são as definitivas
    assert [c["posicao"] for c in d["eleitos"]] == sorted(c["posicao"] for c in d["eleitos"])  # na ordem de votos


def test_distrital_no_df_e_estadual_nos_demais(meio):
    assert json_de(meio.get("/api/v1/proporcional/deputado-distrital/df"))["resultado"]["cargo"]["vagas"] == 24
    assert json_de(meio.get("/api/v1/proporcional/deputado-estadual/sp"))["resultado"]["cargo"]["vagas"] == 94
    assert json_de(meio.get("/api/v1/proporcional/deputado-federal/df"))["resultado"]["cargo"]["vagas"] == 8
    for caminho in ("/deputado-estadual/df", "/deputado-distrital/sp", "/deputado-federal/xx", "/presidente/sp", "/senador/sp",
                    "/deputado-federal/zz"):
        r = meio.get(f"/api/v1/proporcional{caminho}")
        assert r.status_code == 404 and r.get_json()["erro"], caminho


def test_turno_invalido_e_etag(meio):
    assert meio.get("/api/v1/proporcional/deputado-federal/sp?turno=3").status_code == 400
    primeira = meio.get("/api/v1/proporcional/deputado-federal/sp")
    segunda = meio.get("/api/v1/proporcional/deputado-federal/sp", headers={"If-None-Match": primeira.headers["ETag"]})
    assert segunda.status_code == 304 and "X-Defasagem-S" in segunda.headers


def test_uf_sem_dados_ainda_responde_indisponivel_sem_erro(tmp_path):
    app, _, _ = montar_app(tmp_path, 0.5, cargos=(1, 3, 5))  # o poller ainda não trouxe os deputados
    c = app.test_client()
    d = json_de(c.get("/api/v1/proporcional/deputado-federal/sp"))
    assert d["disponivel"] is False and "agrupamentos" not in d
    t = json_de(c.get("/api/v1/proporcional/deputado-federal"))
    assert t["vagas_total"] == 0 and all(u["disponivel"] is False for u in t["ufs"]) and t["distribuicao"] == []
    assert c.get("/api/v1/proporcional/deputado-federal/sp/candidatos").status_code == 404


# ---- API: busca de candidatos --------------------------------------------------------------------------
def test_busca_pagina_por_votos_e_marca_a_posicao(meio):
    d = json_de(meio.get("/api/v1/proporcional/deputado-federal/sp/candidatos"))
    assert d["total"] == 356 and d["pagina"] == 1 and d["paginas"] == 18 and len(d["itens"]) == 20
    assert [c["posicao"] for c in d["itens"]] == list(range(1, 21))
    ultima = json_de(meio.get("/api/v1/proporcional/deputado-federal/sp/candidatos?pagina=18"))
    assert len(ultima["itens"]) == 16 and ultima["itens"][-1]["posicao"] == 356
    assert json_de(meio.get("/api/v1/proporcional/deputado-federal/sp/candidatos?pagina=500"))["pagina"] == 18  # passou do fim: última página


def test_busca_por_nome_ignora_acentos_e_caixa_e_por_numero_usa_prefixo(meio):
    todos = json_de(meio.get("/api/v1/proporcional/deputado-federal/sp/candidatos?q=helio"))
    assert todos["total"] >= 1 and all("HELIO" in c["nome"] or "HELIO" in c["urna"] for c in todos["itens"])
    assert json_de(meio.get("/api/v1/proporcional/deputado-federal/sp/candidatos?q=H%C3%89LIO%20brisa"))["total"] >= 1
    por_numero = json_de(meio.get("/api/v1/proporcional/deputado-federal/sp/candidatos?q=6001"))
    assert por_numero["total"] >= 1 and all(c["numero"].startswith("6001") for c in por_numero["itens"])
    assert json_de(meio.get("/api/v1/proporcional/deputado-federal/sp/candidatos?q=zzzzzz"))["itens"] == []


def test_busca_filtra_por_agrupamento(meio):
    painel = json_de(meio.get("/api/v1/proporcional/deputado-federal/sp"))
    grupo = painel["agrupamentos"][1]
    d = json_de(meio.get(f"/api/v1/proporcional/deputado-federal/sp/candidatos?agr={grupo['id']}"))
    assert d["total"] == grupo["candidatos"] and {c["agr"] for c in d["itens"]} == {grupo["id"]}
    assert json_de(meio.get("/api/v1/proporcional/deputado-federal/sp/candidatos?agr=0"))["total"] == 0


@pytest.mark.parametrize("consulta", ["q=" + "a" * 61, "agr=" + "1" * 21, "pagina=0", "pagina=501", "pagina=x", "pagina=-1"])
def test_busca_rejeita_parametros_invalidos(meio, consulta):
    assert meio.get(f"/api/v1/proporcional/deputado-federal/sp/candidatos?{consulta}").status_code == 400


# ---- API: visão nacional -------------------------------------------------------------------------------
def test_tabela_nacional_do_federal_soma_as_vagas_das_ufs(meio):
    d = json_de(meio.get("/api/v1/proporcional/deputado-federal"))
    assert d["vagas_total"] == 513 == d["vagas_distribuidas"]
    assert len(d["ufs"]) == 27 and all(u["disponivel"] and u["cargo"] == "deputado-federal" for u in d["ufs"])
    assert sum(g["vagas"] for g in d["distribuicao"]) == 513
    ordem = [(-g["vagas"], -g["votos"]) for g in d["distribuicao"]]
    assert ordem == sorted(ordem)
    assert all(g["cor"] in CORES_VALIDAS and g["ufs"] <= 27 for g in d["distribuicao"])
    assert sum(u["vagas"] for u in d["ufs"]) == 513
    sp = next(u for u in d["ufs"] if u["codigo"] == "sp")
    assert sp["vagas"] == 70 and 1 <= len(sp["top"]) <= 3 and sp["mais_votado"]["foto"].startswith("/foto/6259/sp/")
    assert [t["votos"] for t in sp["top"]] == sorted((t["votos"] for t in sp["top"]), reverse=True)
    assert sp["margem_pp"] == pytest.approx(sp["top"][0]["pct"]["n"] - sp["top"][1]["pct"]["n"], abs=0.011)
    assert sp["secoes"]["pst"]["n"] > 0 and sp["final"] is False


def test_tabela_nacional_do_estadual_inclui_o_distrital_do_df(meio):
    d = json_de(meio.get("/api/v1/proporcional/deputado-estadual"))
    assert len(d["ufs"]) == 27 and d["vagas_total"] == d["vagas_distribuidas"] == 1059
    df = [u for u in d["ufs"] if u["cargo"] == "deputado-distrital"]
    assert [u["codigo"] for u in df] == ["df"] and df[0]["vagas"] == 24
    assert sum(g["vagas"] for g in d["distribuicao"]) == 1059


def test_tabela_nacional_so_existe_para_federal_e_estadual(meio):
    for slug in ("deputado-distrital", "presidente", "vereador"):
        assert meio.get(f"/api/v1/proporcional/{slug}").status_code == 404


def test_agrupamento_nacional_pela_chave_junta_federacao_e_partido_isolado(fim):
    """Uma federação conta como um único agrupamento em todas as UFs (chave `f:<número>`), um partido isolado, como `p:<número>`."""
    d = json_de(fim.get("/api/v1/proporcional/deputado-federal"))
    chaves = [g["chave"] for g in d["distribuicao"]]
    assert len(chaves) == len(set(chaves)) and all(c[:2] in ("f:", "p:") for c in chaves)
    assert any(c.startswith("f:") for c in chaves) and any(c.startswith("p:") for c in chaves)
    assert all(u["final"] is True for u in d["ufs"]) and d["vagas_distribuidas"] == d["vagas_total"] == 513


# ---- a página da UF avisa quais deputados existem ----------------------------------------------------------
def test_pagina_da_uf_lista_os_cargos_proporcionais_dela(meio):
    sp = json_de(meio.get("/api/v1/uf/sp"))
    assert [p["slug"] for p in sp["proporcionais"]] == ["deputado-federal", "deputado-estadual"]
    df = json_de(meio.get("/api/v1/uf/df"))
    assert [p["slug"] for p in df["proporcionais"]] == ["deputado-federal", "deputado-distrital"]
    assert [x["slug"] for x in sp["disputas"]] == ["presidente", "governador", "senador"]  # os majoritários seguem à parte


def test_deputados_nao_entram_no_historico_de_evolucao(meio):
    assert meio.get("/api/v1/historico/deputado-federal/sp").status_code in (400, 404)


# ---- 2º turno: Senador e deputados só têm o 1º ---------------------------------------------------------
def test_cargos_de_primeiro_turno_continuam_valendo_depois_que_o_segundo_comeca(tmp_path):
    """Quando o 2º turno começa e vira o padrão, as páginas de Senador e de deputados seguem mostrando o 1º (o único que existe)."""
    import copy

    app, store, _ = montar_app(tmp_path, 1.0)
    cfg = copy.deepcopy(store.get("cfg").dados)
    pleito = cfg["pleitos"][0]
    presidente, estadual = (copy.deepcopy(e) for e in pleito["eleicoes"])
    presidente.update(cd="6258", turno=2, nome="Presidente 2º turno")
    estadual.update(cd="6260", turno=2, nome="Governador 2º turno")
    estadual["abrangencias"] = [{"cd": "sp", "cargos": [{"cd": 3, "nome": "Governador", "tipo": 1}], "municipios": []}]
    pleito["eleicoes"] += [presidente, estadual]
    cfg["idg"] = "9999999"
    store.guardar("cfg", "cfg", cfg, idg=cfg["idg"], etag=None, url="cfg")
    # o 2º turno já tem urnas apuradas: passa a ser o turno padrão
    gov = store.get("u:6259:3:sp").dados
    store.guardar("u:6260:3:sp", "u", gov, idg=gov["idg"], etag=None, url="u", meta={"ele": "6260", "cargo": 3, "abr": "sp"})

    c = app.test_client()
    meta = json_de(c.get("/api/v1/meta"))
    assert meta["turnos"] == [1, 2] and meta["turno_padrao"] == 2
    for caminho in ("/api/v1/cargo/senador", "/api/v1/proporcional/deputado-federal", "/api/v1/proporcional/deputado-estadual"):
        d = json_de(c.get(caminho))
        assert d["turno"] == 1 and d["turnos"] == [1], caminho  # o seletor de turno nem aparece nesses cargos
    d = json_de(c.get("/api/v1/proporcional/deputado-federal/sp"))
    assert d["turno"] == 1 and d["disponivel"] and d["turnos"] == [1]
    assert json_de(c.get("/api/v1/cargo/governador"))["turnos"] == [1, 2]  # quem tem 2º turno segue oferecendo os dois
    for caminho in ("/api/v1/cargo/senador?turno=2", "/api/v1/proporcional/deputado-federal?turno=2", "/api/v1/proporcional/deputado-federal/sp?turno=2"):
        assert c.get(caminho).status_code == 404, caminho  # pedir o 2º turno de quem não tem continua sendo um erro claro
    # na página da UF em 2º turno vêm só as disputas desse turno; os deputados ficam no 1º
    uf = json_de(c.get("/api/v1/uf/sp"))
    assert uf["turno"] == 2 and uf["proporcionais"] == [] and [x["slug"] for x in uf["disputas"]] == ["presidente", "governador"]  # sem o Senador
    uf1 = json_de(c.get("/api/v1/uf/sp?turno=1"))
    assert [p["slug"] for p in uf1["proporcionais"]] == ["deputado-federal", "deputado-estadual"]


# ---- destino do voto: voto anulado não passa despercebido --------------------------------------------------------
def test_destino_do_voto_anulado_chega_a_lista_de_candidatos(tmp_path, fixture_json):
    """O EA20 diz, depois da 1ª totalização parcial, para onde foi o voto do candidato ("Anulado sub judice", por exemplo)."""
    import copy

    from app.config import Settings
    from app.servico import Servico
    from app.store import Store

    dados = copy.deepcopy(fixture_json("ele2026/6259/dados/df/df-c0008-e006259-u.json"))
    candidatos = [c for a in dados["carg"][0]["agr"] for p in a["par"] for c in p["cand"]]
    candidatos[0]["dvt"], candidatos[1]["dvt"], candidatos[2]["dvt"] = "Anulado sub judice", "Válido", "Anulado"
    r = parse.parse_resultado(dados)
    por_sq = {c["sq"]: c for c in r["candidatos"]}
    assert por_sq[candidatos[0]["sqcand"]]["destino"] == "Anulado sub judice" and por_sq[candidatos[1]["sqcand"]]["destino"] == "Válido"

    store = Store()
    cfg = parse.parse_config_eleicoes(fixture_json("comum/config/ele-c.json"))
    store.guardar("cfg", "cfg", cfg, idg=cfg["idg"], etag=None, url="cfg")
    store.guardar("u:6259:8:df", "u", r, idg=r["idg"], etag=None, url="u")
    sv = Servico(Settings(data_dir=tmp_path, iniciar_poller=False), store)
    itens = sv.buscar_candidatos_proporcional("deputado-distrital", "df", tamanho=500)["itens"]
    destinos = {c["sq"]: c["destino"] for c in itens}
    assert destinos[candidatos[0]["sqcand"]] == "Anulado sub judice" and destinos[candidatos[2]["sqcand"]] == "Anulado"
    assert destinos[candidatos[1]["sqcand"]] == ""  # "Válido" é o normal: não vai na resposta
    assert sum(1 for d in destinos.values() if d) == 2


def test_simulador_marca_um_candidato_por_lista_com_voto_anulado(meio, fim):
    for cliente in (meio, fim):
        d = json_de(cliente.get("/api/v1/proporcional/deputado-federal/sp/candidatos?q=indeferido"))
        assert d["total"] == 1 and d["itens"][0]["destino"] == "Anulado sub judice" and not d["itens"][0]["eleito"]
    painel = json_de(meio.get("/api/v1/proporcional/deputado-federal/sp"))
    assert all(c["destino"] == "" for c in painel["destaques"])  # "Válido" é o normal: só o que foge dele aparece
