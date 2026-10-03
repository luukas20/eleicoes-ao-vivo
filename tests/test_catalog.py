from collections import Counter

import pytest

from app.catalog import disputas_ativas, montar_alvos
from app.tse import parse
from app.tse.urls import TseUrls


@pytest.fixture(scope="module")
def config(fixture_json):
    return parse.parse_config_eleicoes(fixture_json("comum/config/ele-c.json"))


def urls_do_ciclo(ciclo):
    return TseUrls("https://resultados.tse.jus.br", "oficial", ciclo)


def test_disputas_do_ciclo_mais_recente(config):
    disputas = disputas_ativas(config)
    por_cargo = {(d.ele, d.cargo.cd): d for d in disputas}
    # 6257 = Presidente; 6259 = Governador, Senador e deputados; 6261 (Conselheiro Distrital) fica de fora
    assert set(por_cargo) == {("6257", 1), ("6259", 3), ("6259", 5), ("6259", 6), ("6259", 7), ("6259", 8)}
    assert all(d.ciclo == "ele2026" and d.turno == 1 and d.pleito == "3220" and d.data == "2026-10-04" for d in disputas)
    assert por_cargo[("6257", 1)].ele_segundo_turno == "6258" and por_cargo[("6259", 3)].ele_segundo_turno == "6260"
    assert [d.nacional for d in disputas if d.nacional] == [True] and por_cargo[("6257", 1)].nacional


def test_ufs_por_cargo(config):
    ufs = {(d.cargo.cd): d.ufs for d in disputas_ativas(config)}
    assert len(ufs[1]) == 28 and "zz" in ufs[1]  # 27 UFs + exterior
    assert len(ufs[3]) == len(ufs[5]) == len(ufs[6]) == 27 and "zz" not in ufs[3]
    assert len(ufs[7]) == 26 and "df" not in ufs[7]  # DF elege Deputado Distrital
    assert ufs[8] == ("df",)


def test_alvos_derivados(config):
    alvos = montar_alvos(disputas_ativas(config), urls_do_ciclo)
    por_tipo = Counter(a.tipo for a in alvos)
    assert por_tipo == {"cm": 2, "ab": 2, "u": 1 + 28 + 27 + 27 + 27 + 26 + 1}
    assert len({a.chave for a in alvos}) == len(alvos)  # chaves únicas

    por_chave = {a.chave: a for a in alvos}
    base = "https://resultados.tse.jus.br/oficial/ele2026"
    assert por_chave["u:6257:1:br"].url == f"{base}/6257/dados/br/br-c0001-e006257-u.json"
    assert por_chave["u:6257:1:br"].camada == "nacional"
    assert por_chave["u:6259:3:sp"].url == f"{base}/6259/dados/sp/sp-c0003-e006259-u.json"
    assert por_chave["u:6259:3:sp"].camada == "uf" and por_chave["u:6259:6:sp"].camada == "uf_lento"
    assert por_chave["u:6259:8:df"].url.endswith("/df-c0008-e006259-u.json")
    assert por_chave["ab:6257:br"].url == f"{base}/6257/dados/br/br-e006257-ab.json"
    assert por_chave["cm:6259"].url == f"{base}/6259/config/mun-e006259-cm.json"
    assert "u:6259:7:df" not in por_chave and "u:6259:3:zz" not in por_chave  # combinações que não existem


def test_so_restringe_as_eleicoes(config):
    disputas = disputas_ativas(config, so=("6259",))
    assert {d.ele for d in disputas} == {"6259"} and len(disputas) == 5


def test_segundo_turno_por_uf_so_cria_alvos_das_ufs_listadas():
    config = {"pleitos": [{"cd": "9", "ciclo": "ele2026", "data": "2026-10-25", "eleicoes": [
        {"cd": "6260", "cdt2": None, "turno": 2, "tipo": 1, "abrangencias": [
            {"cd": "sp", "cargos": [{"cd": 3, "nome": "Governador", "tipo": 1}], "municipios": []},
            {"cd": "rj", "cargos": [{"cd": 3, "nome": "Governador", "tipo": 1}], "municipios": []},
        ]},
    ]}]}
    disputas = disputas_ativas(config)
    assert [(d.ele, d.turno, d.ufs) for d in disputas] == [("6260", 2, ("sp",)), ("6260", 2, ("rj",))]
    chaves = {a.chave for a in montar_alvos(disputas, urls_do_ciclo) if a.tipo == "u"}
    assert chaves == {"u:6260:3:sp", "u:6260:3:rj"}
