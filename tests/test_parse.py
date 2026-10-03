import json

import pytest

from app.tse import parse as p


# ---- utilitários -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "valor, esperado",
    [("158745502", 158745502), ("0", 0), ("", 0), (None, 0), (" 42 ", 42), (7, 7), ("10,0", 10), ("abc", 0), (True, 0)],
)
def test_to_int(valor, esperado):
    assert p.to_int(valor) == esperado


@pytest.mark.parametrize(
    "valor, esperado",
    [
        ("45,32", 45.32), ("100,00", 100.0), ("0", 0.0), ("45.321234567", 45.321234567),
        ("1.234,5", 1234.5), ("1.234.567", 1234567.0), ("", 0.0), (None, 0.0), ("x", 0.0), (12.5, 12.5),
    ],
)
def test_to_float_aceita_virgula_e_ponto(valor, esperado):
    assert p.to_float(valor) == pytest.approx(esperado)


def test_data_hora_em_horario_de_brasilia():
    momento = p.parse_data_hora("02/10/2026", "20:13:54")
    assert p.iso(momento) == "2026-10-02T20:13:54-03:00"
    assert p.parse_data_hora("", "") is None
    assert p.parse_data_hora("32/13/2026", "99:00:00") is None
    assert p.parse_data("04/10/2026") == "2026-10-04" and p.parse_data("lixo") is None


def test_sem_acentos():
    assert p.sem_acentos("SÃO LUÍS") == "sao luis"


def test_decodificar_aceita_bom_e_recusa_nao_objeto():
    assert p.decodificar(b"\xef\xbb\xbf" + '{"a": "ç"}'.encode("utf-8")) == {"a": "ç"}
    with pytest.raises(ValueError):
        p.decodificar(b"[1, 2]")


def test_normalizar_bloco_une_percentual_e_gemeo_numerico():
    bloco = {"vv": "90", "pvv": "90,00", "pvvn": "90.123456789", "tv": "100", "vsan": ""}
    saida = p.normalizar_bloco(bloco, p.V_PARES)
    assert saida["vv"] == 90 and saida["tv"] == 100 and saida["vsan"] == 0
    assert saida["pvv"] == {"t": "90,00", "n": pytest.approx(90.123456789)}  # t como publicado, n = 9 casas
    assert "pvvn" not in saida


def test_normalizar_bloco_sem_gemeo_usa_o_proprio_texto():
    assert p.normalizar_bloco({"pst": "12,50"}, p.S_PARES) == {"pst": {"t": "12,50", "n": 12.5}}


# ---- EA11 (feed real, 02/10/2026) --------------------------------------------------------------
def test_config_eleicoes_real(fixture_json):
    cfg = p.parse_config_eleicoes(fixture_json("comum/config/ele-c.json"))
    assert cfg["fase"] == "o" and cfg["idg"] == "980407" and cfg["gerado_em"] == "2026-10-02T18:30:57-03:00"
    assert set(cfg["dirs"]) == {"ab", "aux", "cm", "cs", "e", "ft", "u"}
    assert len(cfg["pleitos"]) == 42

    pleito = next(x for x in cfg["pleitos"] if x["ciclo"] == "ele2026")
    assert (pleito["cd"], pleito["data"]) == ("3220", "2026-10-04")
    por_codigo = {e["cd"]: e for e in pleito["eleicoes"]}
    assert set(por_codigo) == {"6257", "6259", "6261"}
    assert (por_codigo["6257"]["cdt2"], por_codigo["6259"]["cdt2"], por_codigo["6261"]["cdt2"]) == ("6258", "6260", None)

    def cargos(ele):
        return [c["cd"] for a in por_codigo[ele]["abrangencias"] for c in a["cargos"]]

    assert cargos("6257") == [1] and cargos("6259") == [3, 5, 6, 7, 8]
    assert por_codigo["6257"]["turno"] == 1 and por_codigo["6257"]["abrangencias"][0]["cd"] == "br"


# ---- EA20 (feed real, pré-eleição: tudo zerado) --------------------------------------------------
def test_resultado_presidente_br_real(fixture_json):
    r = p.parse_resultado(fixture_json("ele2026/6257/dados/br/br-c0001-e006257-u.json"))
    assert (r["ele"], r["turno"], r["fase"], r["idg"]) == ("6257", 1, "o", "1026910")
    assert r["gerado_em"] == "2026-10-02T20:13:54-03:00" and r["totalizado_em"] is None
    assert r["abrangencia"] == {"tipo": "br", "codigo": "br"}
    assert r["cargo"]["cd"] == 1 and r["cargo"]["nome"] == "Presidente" and r["cargo"]["vagas"] == 1
    assert r["cargo"]["quociente_eleitoral"] is None and r["agremiacoes"] == []

    # apuração não iniciada: 'dv' já é 's', então o estado vem de andamento/seções
    assert r["estado"]["andamento"] == "n" and r["estado"]["divulga"] is True
    assert r["estado"]["totalizacao_final"] is False and r["estado"]["definido"] is None
    assert r["secoes"]["ts"] == 499248 and r["secoes"]["st"] == 0
    assert r["secoes"]["pst"] == {"t": "0,00", "n": 0.0} and r["secoes"]["psnt"] == {"t": "100,00", "n": 100.0}
    assert r["eleitorado"]["te"] == 158745502 and r["eleitorado"]["c"] == 0
    assert r["votos"]["tv"] == 0 and r["votos"]["pvv"] == {"t": "0,00", "n": 0.0}

    assert len(r["candidatos"]) == 12
    assert [c["seq"] for c in r["candidatos"]] == list(range(1, 13))  # sem votos: ordem da urna
    assert all(c["votos"] == 0 and c["pct"]["t"] == "0,00" and not c["eleito"] for c in r["candidatos"])
    assert all(c["sq"].isdigit() and c["numero"] and c["urna"] and c["partido"] and c["vice"] for c in r["candidatos"])
    coligacao = next(c for c in r["candidatos"] if c["agremiacao_tipo"] == "c")
    assert " / " in coligacao["composicao"]


def test_resultado_governador_sp_real(fixture_json):
    r = p.parse_resultado(fixture_json("ele2026/6259/dados/sp/sp-c0003-e006259-u.json"))
    assert r["abrangencia"] == {"tipo": "uf", "codigo": "sp"}
    assert r["cargo"]["cd"] == 3 and r["cargo"]["nome_feminino"] == "Governadora"
    assert len(r["candidatos"]) == 5 and r["estado"]["andamento"] == "n"


def test_resultado_municipio_e_exterior_reais(fixture_json):
    m = p.parse_resultado(fixture_json("ele2026/6257/dados/sp/sp71072-c0001-e006257-u.json"))
    assert m["abrangencia"] == {"tipo": "mu", "codigo": "71072"} and m["secoes"]["ts"] == 26683
    z = p.parse_resultado(fixture_json("ele2026/6257/dados/zz/zz-c0001-e006257-u.json"))
    assert z["abrangencia"] == {"tipo": "uf", "codigo": "zz"} and z["eleitorado"]["te"] == 916534


# ---- EA14 (feed real) ---------------------------------------------------------------------------
def test_acompanhamento_br_real(fixture_json):
    ab = p.parse_acompanhamento(fixture_json("ele2026/6257/dados/br/br-e006257-ab.json"))
    assert (ab["ele"], ab["turno"], ab["fase"], ab["idg"]) == ("6257", 1, "o", "962221")
    assert len(ab["abrangencias"]) == 29  # BR + 27 UFs + exterior

    br = next(a for a in ab["abrangencias"] if a["tipo"] == "br")
    ufs = [a for a in ab["abrangencias"] if a["tipo"] == "uf"]
    assert len(ufs) == 28 and {a["codigo"] for a in ufs} >= {"sp", "zz", "ac"}
    assert br["secoes"]["ts"] == sum(a["secoes"]["ts"] for a in ufs) == 499248  # UFs somam o Brasil
    assert br["eleitorado"]["te"] == sum(a["eleitorado"]["te"] for a in ufs) == 158745502
    assert br["andamento"] == "n" and br["atualizado_em"] is None
    assert br["contagem"]["ufsnr"] == 28 and br["contagem"]["pufsnr"] == {"t": "100,00", "n": 100.0}
    ac = next(a for a in ufs if a["codigo"] == "ac")
    assert ac["secoes"]["ts"] == 2270 and ac["contagem"]["munnr"] == 22


# ---- cargo proporcional (sintético, no formato do EA20) ------------------------------------------
def _proporcional() -> dict:
    def cand(n, nome, vap, e="n", st="", seq=1):
        return {"n": n, "sqcand": f"9{n}", "nm": nome, "nmu": nome, "dt": "01/01/1980", "seq": str(seq),
                "e": e, "st": st, "vap": str(vap), "pvap": "1,00", "pvapn": "1.000000000"}

    return {
        "ele": "6259", "t": "1", "f": "s", "sup": "n", "tpabr": "uf", "cdabr": "SP", "idg": "1",
        "dg": "03/10/2026", "hg": "10:00:00", "dt": "04/10/2026", "ht": "19:00:00", "dv": "s", "tf": "n", "and": "p",
        "carg": [{
            "cd": "6", "nmn": "Deputado Federal", "nmm": "Deputado Federal", "nmf": "Deputada Federal", "nv": "70", "qe": "300000",
            "agr": [
                {"n": "1", "nm": "Federação A", "tp": "f", "com": "AA/BB", "tvtn": "500", "tvtl": "100", "vag": "2", "par": [
                    {"n": "11", "sg": "AA", "nm": "Partido A", "tvtn": "300", "tvtl": "60",
                     "cand": [cand("1101", "Ana", 200, "s", "Eleito", 1), cand("1102", "Bia", 100, "n", "", 2)]},
                    {"n": "22", "sg": "BB", "nm": "Partido B", "tvtn": "200", "tvtl": "40", "cand": [cand("2201", "Caio", 200, "s", "Eleito por QP", 3)]},
                ]},
                {"n": "33", "nm": "Partido C", "tp": "i", "vag": "1", "par": [
                    {"n": "33", "sg": "CC", "nm": "Partido C", "tvtn": "900", "tvtl": "50", "cand": [cand("3301", "Davi", 900, "s", "Eleito por média", 4)]},
                ]},
            ],
        }],
        "s": {"ts": "10", "st": "5", "pst": "50,00", "pstn": "50.000000000"},
    }


def test_resultado_proporcional_sintetico():
    r = p.parse_resultado(_proporcional())
    assert r["fase"] == "s" and r["abrangencia"]["codigo"] == "sp"  # UF sempre em minúsculas
    assert r["cargo"]["quociente_eleitoral"] == 300000 and r["cargo"]["vagas"] == 70
    assert [c["urna"] for c in r["candidatos"]] == ["Davi", "Ana", "Caio", "Bia"]  # por votos; empate (200) -> ordem da urna
    assert [c["situacao"] for c in r["candidatos"]][:3] == ["Eleito por média", "Eleito", "Eleito por QP"]
    assert r["totalizado_em"] == "2026-10-04T19:00:00-03:00" and r["secoes"]["pst"] == {"t": "50,00", "n": 50.0}

    # agremiações ordenadas por votos totais: Partido C (950) > Federação A (600)
    assert [x["nome"] for x in r["agremiacoes"]] == ["Partido C", "Federação A"]
    por_nome = {x["nome"]: x for x in r["agremiacoes"]}
    assert por_nome["Federação A"]["votos_total"] == 600 and por_nome["Federação A"]["vagas"] == 2
    # partido isolado ('i') não tem totais no nível da agremiação: soma dos partidos
    assert por_nome["Partido C"]["votos_nominais"] == 900 and por_nome["Partido C"]["votos_legenda"] == 50


def test_resultado_sem_cargo_nao_quebra():
    r = p.parse_resultado({"ele": "1", "t": "2", "f": "o", "tpabr": "br", "cdabr": "br"})  # ex.: consulta popular
    assert r["cargo"] is None and r["candidatos"] == [] and r["turno"] == 2


# ---- EA10 (sintético, no formato da especificação) -----------------------------------------------
def test_eleitos_sintetico():
    dados = {
        "ele": "6259", "cdabr": "BR", "nmabr": "Brasil", "t": "1", "f": "o", "cdcar": "3", "nmcar": "Governador",
        "dg": "04/10/2026", "hg": "21:00:00", "idg": "7",
        "abr": [{
            "dt": "04/10/2026", "ht": "20:30:00", "tpabr": "uf", "cdabr": "SP", "nmabr": "SÃO PAULO", "tvap": "1000",
            "scv": "n", "esae": "n", "mnae": [],
            "cand": [{"n": "10", "sqcand": "1", "nm": "Fulano de Tal", "nmu": "Fulano", "sgp": "XYZ", "com": "XYZ/ABC",
                      "vap": "600", "seq": "1", "vs": [{"tp": "v", "sqcand": "2", "nm": "Vice Nome", "nmu": "Vice", "sgp": "XYZ"}]}],
        }],
    }
    r = p.parse_eleitos(dados)
    assert r["cargo"] == {"cd": 3, "nome": "Governador"} and r["abrangencia"]["codigo"] == "br"
    a = r["abrangencias"][0]
    assert a["codigo"] == "sp" and a["votos_computados"] == 1000 and not a["sem_eleito"]
    assert a["eleitos"][0]["urna"] == "Fulano" and a["eleitos"][0]["vice"] == "Vice" and a["eleitos"][0]["votos"] == 600


def test_municipios_sintetico():
    dados = {"dg": "02/10/2026", "hg": "18:30:22", "idg": "5", "f": "o", "abr": [
        {"cd": "sp", "ds": "SÃO PAULO", "mu": [{"cd": "71072", "cdi": "3550308", "nm": "SÃO PAULO", "c": "s", "z": ["0001", "0002"]},
                                              {"cd": "62919", "cdi": "3548708", "nm": "SÃO BERNARDO DO CAMPO", "c": "n", "z": ["0003"]}]}]}
    r = p.parse_municipios(dados)
    sp = r["ufs"]["sp"]
    assert sp["nome"] == "SÃO PAULO" and len(sp["municipios"]) == 2
    assert sp["municipios"][0]["capital"] is True and sp["municipios"][0]["zonas"] == ["0001", "0002"]
    assert sp["municipios"][1]["busca"] == "sao bernardo do campo"
