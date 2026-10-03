"""Mapa geográfico: o gerador (tools/gerar_mapa.py) e o arquivo de contornos que o painel serve."""
import json
import math
import re
from pathlib import Path

import pytest

from app.tse.dominio import UF_NOMES, UFS
from tools import gerar_mapa as gm

ARQUIVO = Path(__file__).resolve().parent.parent / "app" / "static" / "data" / "mapa-ufs.json"
NUMERO = r"-?\d+"


@pytest.fixture(scope="module")
def mapa():
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


def aneis_do_caminho(d: str) -> list[list[tuple[int, int]]]:
    """Desfaz o caminho `M x y l dx dy …z` (relativo) em listas de vértices absolutos."""
    aneis = []
    for m in re.finditer(rf"M({NUMERO}) ({NUMERO})l([-\d ]+)z", d):
        x, y = int(m.group(1)), int(m.group(2))
        numeros = [int(n) for n in re.findall(NUMERO, m.group(3))]
        anel = [(x, y)]
        for dx, dy in zip(numeros[0::2], numeros[1::2]):
            x, y = x + dx, y + dy
            anel.append((x, y))
        aneis.append(anel)
    return aneis


def dentro(p, aneis) -> bool:
    """Par-ímpar sobre todos os anéis da UF."""
    x, y = p
    resultado = False
    for anel in aneis:
        for (xa, ya), (xb, yb) in zip(anel, anel[1:] + anel[:1]):
            if (ya > y) != (yb > y) and x < xa + (y - ya) * (xb - xa) / (yb - ya):
                resultado = not resultado
    return resultado


# ---- o arquivo de contornos ----------------------------------------------------------------------------------
def test_arquivo_tem_as_27_ufs_em_ordem_alfabetica_do_nome(mapa):
    siglas = [u["uf"] for u in mapa["ufs"]]
    assert sorted(siglas) == sorted(UFS) and len(siglas) == 27
    assert siglas == sorted(UFS, key=lambda s: gm.sem_acento(UF_NOMES[s]))  # é a ordem do Tab no mapa
    assert all(u["nome"] == UF_NOMES[u["uf"]] for u in mapa["ufs"])


def test_arquivo_e_pequeno_o_bastante_para_baixar_junto_com_a_pagina():
    assert ARQUIVO.stat().st_size < 40_000


def test_cada_uf_tem_forma_ancora_e_largura_de_rotulo_validas(mapa):
    for u in mapa["ufs"]:
        aneis = aneis_do_caminho(u["d"])
        assert aneis, u["uf"]
        assert re.fullmatch(rf"(M{NUMERO} {NUMERO}l[-\d ]+z)+", u["d"]), u["uf"]
        for anel in aneis:
            assert len(anel) >= 3 and abs(gm.area_assinada(anel)) > 1
            assert all(0 <= x <= mapa["largura"] and 0 <= y <= mapa["altura"] for x, y in anel), u["uf"]
        assert dentro((u["x"], u["y"]), aneis), f"{u['uf']}: o rótulo cairia fora do estado"
        assert u["lw"] > 0 and u["e"] >= u["x"], u["uf"]


def test_so_as_ufs_pequenas_tem_chamada_e_o_resto_comporta_o_rotulo(mapa):
    com = {u["uf"] for u in mapa["ufs"] if u.get("chamada")}
    assert com == set(gm.COM_CHAMADA) and com <= set(UFS)
    menor_sem = min(u["lw"] for u in mapa["ufs"] if u["uf"] not in com)
    assert max(u["lw"] for u in mapa["ufs"] if u["uf"] in com) <= menor_sem


def test_as_areas_guardam_as_proporcoes_reais(mapa):
    """A projeção é equivalente (preserva área): os tamanhos relativos têm de bater com os reais (km²)."""
    area = {u["uf"]: u["area"] for u in mapa["ufs"]}
    reais = {"am": 1_559_256, "pa": 1_245_871, "mt": 903_208, "mg": 586_513, "ba": 564_760, "rs": 281_707, "sp": 248_219, "pr": 199_308}
    for uf, km2 in reais.items():
        esperado = km2 / reais["am"]
        assert area[uf] / area["am"] == pytest.approx(esperado, rel=0.06), uf


def test_estados_vizinhos_se_encaixam_sem_frestas(mapa):
    """Fronteira entre duas UFs é a mesma sequência de vértices nas duas: nenhuma fresta, nenhuma sobreposição."""
    donos: dict[frozenset, set[str]] = {}
    for u in mapa["ufs"]:
        for anel in aneis_do_caminho(u["d"]):
            for a, b in zip(anel, anel[1:] + anel[:1]):
                donos.setdefault(frozenset((a, b)), set()).add(u["uf"])
    compartilhadas = [d for d in donos.values() if len(d) == 2]
    assert not any(len(d) > 2 for d in donos.values())
    assert len(compartilhadas) > 150
    pares = {frozenset(d) for d in compartilhadas}
    for a, b in [("sp", "mg"), ("sp", "pr"), ("go", "df"), ("pa", "mt"), ("am", "pa"), ("rs", "sc"), ("ba", "se"), ("ac", "am")]:
        assert frozenset((a, b)) in pares, f"{a} e {b} deveriam dividir uma fronteira"


def test_gitignore_nao_esconde_o_arquivo_do_mapa():
    """`data/` sem a barra inicial ignoraria também app/static/data/ e o mapa não iria para o repositório."""
    linhas = [linha.strip() for linha in (ARQUIVO.parents[3] / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert "data/" not in linhas and "/data/" in linhas


# ---- as peças do gerador -------------------------------------------------------------------------------------------
def test_douglas_peucker_remove_o_que_e_colinear_e_guarda_os_extremos():
    reta = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
    assert gm.douglas_peucker(reta, 0.1) == [(0.0, 0.0), (3.0, 0.0)]
    pico = [(0.0, 0.0), (1.0, 5.0), (2.0, 0.0)]
    assert gm.douglas_peucker(pico, 1.0) == pico


def test_albers_e_equivalente_e_centrado_no_meridiano_central():
    proj = gm.Albers()
    assert proj(-54.0, -12.0) == pytest.approx((0.0, 0.0), abs=1e-9)
    x, y = proj(-54.0, -30.0)
    assert x == pytest.approx(0.0, abs=1e-9) and y < 0  # o sul fica abaixo
    assert proj(-40.0, -12.0)[0] > 0 > proj(-70.0, -12.0)[0]
    # 1° x 1° vale menos área longe do equador, mas a projeção de ÁREA tem de refletir isso (cos φ)
    def celula(lat):
        pts = [proj(-50, lat), proj(-49, lat), proj(-49, lat + 1), proj(-50, lat + 1)]
        return abs(gm.area_assinada(pts))
    assert celula(-30) / celula(0) == pytest.approx(math.cos(math.radians(30)), rel=0.02)


def test_caminho_svg_ida_e_volta():
    aneis = [[(10, 10), (20, 12), (15, 30), (-0, 25)], [(100, 100), (110, 100), (110, 90)]]
    assert aneis_do_caminho(gm.caminho_svg(aneis)) == aneis


def test_simplificar_por_arcos_mantem_a_fronteira_igual_nos_dois_lados():
    # dois quadrados lado a lado; a fronteira (x=10) tem vértices "ruidosos" que a simplificação vai tirar
    fronteira = [(10.0 + (0.05 if y % 2 else 0.0), float(y)) for y in range(0, 11)]
    esq = [(0.0, 0.0)] + fronteira + [(0.0, 10.0)]
    dir_ = [(20.0, 0.0), (20.0, 10.0)] + fronteira[::-1]  # a fronteira é percorrida ao contrário pelo vizinho
    simples = gm.simplificar_aneis({"a": [esq], "b": [dir_]}, eps=0.5)
    comum_a = {p for p in simples["a"][0] if p[0] in (10.0, 10.05)}
    comum_b = {p for p in simples["b"][0] if p[0] in (10.0, 10.05)}
    assert comum_a == comum_b and len(comum_a) < len(fronteira)  # simplificou, e igual nos dois


def test_posicao_do_rotulo_cabe_a_maior_caixa_dentro_de_um_retangulo():
    largura, altura = 140, 60
    dono = bytearray([255]) * (largura * altura)
    gm.pintar([[(10, 10), (110, 10), (110, 50), (10, 50)]], dono, largura, altura, 0)  # 100 x 40
    pos = gm.melhor_posicao_do_rotulo(dono, largura, altura, 0)
    assert abs(pos["x"] - 60) <= 3 and abs(pos["y"] - 30) <= 3
    assert 0.9 * 40 * gm.PROPORCAO_ROTULO <= pos["lw"] <= 40 * gm.PROPORCAO_ROTULO + 1  # limitada pela altura
    assert pos["e"] == 110


def test_gerar_com_malha_sintetica_produz_todas_as_ufs(monkeypatch):
    monkeypatch.setattr(gm, "LARGURA", 240.0)  # raster pequeno: o teste fica rápido
    codigos = list(gm.SIGLAS)
    features = []
    for i, codigo in enumerate(codigos):
        lon, lat = -70.0 + (i % 6) * 6, 2.0 - (i // 6) * 6  # quadrados de 5° separados por 1°
        anel = [[lon, lat], [lon + 5, lat], [lon + 5, lat - 5], [lon, lat - 5], [lon, lat]]
        features.append({"type": "Feature", "properties": {"codarea": codigo}, "geometry": {"type": "Polygon", "coordinates": [anel]}})
    saida = gm.gerar({"type": "FeatureCollection", "features": features})
    assert {u["uf"] for u in saida["ufs"]} == set(gm.SIGLAS.values())
    for u in saida["ufs"]:
        assert dentro((u["x"], u["y"]), aneis_do_caminho(u["d"])) and u["lw"] > 0
    assert saida["largura"] > 200 and saida["altura"] > 200


def test_gerar_recusa_malha_sem_todas_as_ufs():
    with pytest.raises(ValueError, match="ausentes"):
        gm.gerar({"type": "FeatureCollection", "features": []})


# ---- servido pelo painel ----------------------------------------------------------------------------------------------
def test_painel_serve_o_arquivo_do_mapa_com_a_csp_estrita(novo_app):
    app, _, _ = novo_app(0.5)
    resp = app.test_client().get("/static/data/mapa-ufs.json")
    assert resp.status_code == 200 and resp.mimetype == "application/json"
    assert len(resp.get_json()["ufs"]) == 27
    assert "script-src 'self'" in resp.headers["Content-Security-Policy"]
