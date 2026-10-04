"""Cores dos partidos: reconhecimento das siglas, atribuição por disputa, qualidade da paleta e CSS gerado."""
import itertools
import random
import re

import pytest

from app import cores, partidos
from tools import gerar_css_partidos as gerador

HEX = re.compile(r"^#[0-9A-F]{6}$")
PAPEL = "#F4F1EA"  # fundo claro da página (app.css)
NOITE = "#12141B"  # fundo escuro da página (app.css)


# ---- siglas -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("sigla, esperado", [
    ("PT", "PT"), ("pt", "PT"), ("PL", "PL"), ("PC do B", "PCdoB"), ("PCDOB", "PCdoB"), ("UNIÃO", "UNIÃO"), ("União", "UNIÃO"), ("UNIAO", "UNIÃO"),
    ("REPUBLICANOS", "Republicanos"), ("MISSÃO", "MISSÃO"), ("MISSAO", "MISSÃO"), ("DEMOCRATA", "Democrata"), ("AVANTE", "Avante"),
    ("PODE", "PODE"), ("PODEMOS", "PODE"), ("PMB", "Democrata"), ("PRB", "Republicanos"), ("SOLIDARIEDADE", "Solidariedade"),
    ("REDE", "REDE"), ("NOVO", "NOVO"), ("PSOL", "PSOL"), ("UP", "UP"),
])
def test_reconhece_as_siglas_do_feed_e_apelidos(sigla, esperado):
    assert partidos.partido_de(sigla) == esperado


@pytest.mark.parametrize("sigla", ["", "XYZ", "PAL", None])
def test_sigla_desconhecida_nao_vira_partido(sigla):
    assert partidos.partido_de(sigla) is None and partidos.chave_de(sigla) is None


def test_chaves_de_cor():
    assert partidos.chave_de("PT") == "pt" and partidos.chave_de("PT", alternativa=True) == "pt-alt"
    assert partidos.chave_de("PC do B") == "pcdob" and partidos.chave_de("UNIÃO") == "uniao" and partidos.chave_de("MISSÃO") == "missao"


def test_cor_estavel_do_partido_ignora_variantes_e_nunca_falha():
    assert partidos.chave_do_partido("PT") == "pt" and partidos.chave_do_partido("PC do B") == "pcdob"
    desconhecida = partidos.chave_do_partido("XPTO")
    assert desconhecida in partidos.RESERVA and partidos.chave_do_partido("XPTO") == desconhecida  # sempre a mesma para a mesma sigla
    assert partidos.chave_do_partido("") == "neutro" and partidos.chave_do_partido(None) == "neutro"


def test_todo_apelido_aponta_para_um_partido_da_tabela():
    assert all(alvo in partidos.PARTIDOS for alvo in partidos.APELIDOS.values())
    assert all(partidos.partido_de(apelido) == alvo for apelido, alvo in partidos.APELIDOS.items())


def test_os_30_partidos_registrados_tem_cor():
    registrados = {"MDB", "PT", "PP", "PRD", "PSDB", "PDT", "UNIÃO", "PL", "PODE", "PSB", "Republicanos", "PSD", "Cidadania", "PCdoB",
                   "Solidariedade", "PV", "PSOL", "Avante", "Agir", "DC", "PRTB", "NOVO", "REDE", "Democrata", "MISSÃO", "UP", "PSTU", "PCB", "PCO",
                   "MOBILIZA"}
    assert {partidos.partido_de(s) for s in registrados} == registrados  # cada sigla é reconhecida como ela mesma
    assert registrados == set(partidos.PARTIDOS)


def test_prioridade_so_cita_partidos_da_tabela_e_sem_repetir():
    assert set(partidos.PRIORIDADE) <= set(partidos.PARTIDOS) and len(set(partidos.PRIORIDADE)) == len(partidos.PRIORIDADE)
    assert set(partidos.PARTIDOS) == set(partidos.PRIORIDADE)  # ninguém fica de fora da ordem de desempate


# ---- qualidade da paleta ----------------------------------------------------------------------------------
def test_todas_as_cores_sao_hex_validos_e_as_chaves_nao_se_repetem():
    todas = partidos.todas_as_chaves()
    assert len(todas) == len(partidos.PARTIDOS) * 2 + len(partidos.RESERVA) + 1
    for chave, (claro, escuro) in todas.items():
        assert HEX.match(claro) and HEX.match(escuro), chave
        assert re.fullmatch(r"[a-z0-9]+(-alt)?", chave), chave


def test_o_texto_sobre_cada_cor_tem_contraste_de_leitura_nos_dois_temas():
    """Siglas dentro do mapa e chips: 4,5:1 (WCAG AA) com a tinta que o gerador escolhe (branco ou escura)."""
    for chave, variantes in partidos.todas_as_chaves().items():
        for modo, cor in zip(("claro", "escuro"), variantes):
            tinta = gerador.tinta_sobre(cor)
            assert gerador.contraste(cor, tinta) >= 4.5, f"{chave} ({modo}) {cor} com {tinta}: {gerador.contraste(cor, tinta):.2f}"


def test_no_tema_escuro_as_marcas_se_destacam_do_fundo():
    """Barras e linhas sobre o fundo escuro: ao menos 3:1 (WCAG 1.4.11), exceto o 'neutro' de propósito discreto."""
    for chave, (_, escuro) in partidos.todas_as_chaves().items():
        if chave != "neutro":
            assert gerador.contraste(escuro, NOITE) >= 3.0, f"{chave}: {escuro} sobre o fundo escuro"


def test_as_cores_dos_partidos_principais_sao_bem_distintas_entre_si():
    principais = ["pt", "pl", "psd", "novo", "mdb", "republicanos", "psb", "psol"]
    for a, b in itertools.combinations(principais, 2):
        claro = cores.distancia(partidos.hex_claro(a), partidos.hex_claro(b))
        assert claro >= 10, f"{a} x {b}: {claro:.1f}"


def test_a_cor_de_cada_partido_lembra_a_marca_dele():
    """Salvaguarda de identidade: o tom (matiz) de cada partido conhecido continua na família esperada."""
    def matiz(hexa):
        L, a, b = cores.oklab(hexa)
        import math
        return math.degrees(math.atan2(b, a)) % 360

    assert 0 <= matiz(partidos.hex_claro("pt")) <= 40 or matiz(partidos.hex_claro("pt")) >= 340  # vermelho
    assert 245 <= matiz(partidos.hex_claro("pl")) <= 290  # azul
    assert 40 <= matiz(partidos.hex_claro("novo")) <= 65  # laranja
    assert 70 <= matiz(partidos.hex_claro("psd")) <= 100  # âmbar
    assert 140 <= matiz(partidos.hex_claro("mdb")) <= 185  # verde
    assert 295 <= matiz(partidos.hex_claro("psol")) <= 330  # violeta


# ---- atribuição por disputa ---------------------------------------------------------------------------------
def cands(*siglas):
    return [{"sq": str(1000 + i), "partido": s} for i, s in enumerate(siglas)]


def test_candidato_fica_com_a_cor_do_proprio_partido():
    m = cores.atribuir(cands("PT", "PL", "PSD", "NOVO"))
    assert [m[str(1000 + i)] for i in range(4)] == ["pt", "pl", "psd", "novo"]


def test_a_atribuicao_nao_depende_da_ordem_dos_candidatos():
    lista = cands("PT", "PL", "PSD", "NOVO", "PSTU", "PCB", "PCO", "UP", "MISSÃO", "DC", "AVANTE", "DEMOCRATA")
    esperado = cores.atribuir(lista)
    for _ in range(20):
        embaralhada = lista[:]
        random.shuffle(embaralhada)
        assert cores.atribuir(embaralhada) == esperado


def test_partidos_de_cor_parecida_na_mesma_disputa_ganham_cores_diferentes():
    m = cores.atribuir(cands("PT", "PSTU", "PCB", "PCO", "UP"))  # cinco partidos de esquerda, quase todos vermelhos
    escolhidas = list(m.values())
    assert len(set(escolhidas)) == 5
    assert m["1000"] == "pt"  # o mais conhecido mantém a cor própria
    for a, b in itertools.combinations(escolhidas, 2):
        assert cores.distancia(partidos.hex_claro(a), partidos.hex_claro(b)) >= cores.LIMITE_MINIMO, (a, b)


def test_dois_candidatos_do_mesmo_partido_nao_repetem_a_cor():
    m = cores.atribuir(cands("PL", "PL", "PT"))
    assert {m["1000"], m["1001"]} == {"pl", "pl-alt"} and m["1002"] == "pt"


def test_sigla_desconhecida_recebe_cor_de_reserva_estavel():
    m = cores.atribuir(cands("PT", "XPTO", "ZZZ"))
    assert m["1000"] == "pt" and m["1001"] in partidos.RESERVA and m["1002"] in partidos.RESERVA and m["1001"] != m["1002"]
    assert cores.atribuir(cands("PT", "XPTO", "ZZZ")) == m


def test_disputa_real_do_presidente_2026_tem_cores_distintas_e_fieis(fixture_json):
    from app.tse import parse

    r = parse.parse_resultado(fixture_json("ele2026/6257/dados/br/br-c0001-e006257-u.json"))
    por_partido = {c["partido"]: cores.atribuir(r["candidatos"])[c["sq"]] for c in r["candidatos"]}
    assert len(r["candidatos"]) == 12 and len(set(por_partido.values())) == 12
    assert {s: por_partido[s] for s in ("PT", "PL", "PSD", "NOVO")} == {"PT": "pt", "PL": "pl", "PSD": "psd", "NOVO": "novo"}
    for a, b in itertools.combinations(["pt", "pl", "psd", "novo"], 2):  # os que podem liderar na noite
        assert cores.distancia(partidos.hex_claro(a), partidos.hex_claro(b)) >= 10


def test_disputa_real_de_governador_de_sp(fixture_json):
    from app.tse import parse

    r = parse.parse_resultado(fixture_json("ele2026/6259/dados/sp/sp-c0003-e006259-u.json"))
    m = cores.atribuir(r["candidatos"])
    por_urna = {c["urna"]: m[c["sq"]] for c in r["candidatos"]}
    assert por_urna["FERNANDO HADDAD"] == "pt" and por_urna["TARCÍSIO"] == "republicanos" and len(set(m.values())) == 5


# ---- CSS gerado ---------------------------------------------------------------------------------------------
def test_o_css_dos_partidos_esta_em_dia_com_a_tabela():
    assert gerador.DESTINO.read_text(encoding="utf-8") == gerador.css(), "rode: python -m tools.gerar_css_partidos"
    assert gerador.main(["--conferir"]) == 0


def test_o_css_tem_uma_regra_por_cor_e_os_dois_temas():
    texto = gerador.DESTINO.read_text(encoding="utf-8")
    for chave in partidos.todas_as_chaves():
        assert f'[data-cor="{chave}"]' in texto
        assert texto.count(f"--c-{chave}:") == 3  # claro, escuro por preferência do sistema, escuro forçado pelo botão
    assert '@media (prefers-color-scheme: dark)' in texto and ':root[data-tema="escuro"]' in texto
