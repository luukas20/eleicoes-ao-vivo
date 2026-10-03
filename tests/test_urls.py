import pytest

from app.tse.urls import TseUrls, como_jws

B = "https://resultados.tse.jus.br/oficial"


@pytest.fixture
def urls():
    return TseUrls("https://resultados.tse.jus.br", "oficial", "ele2026")


# ---- exemplos de nomes de arquivo dos PDFs do TSE ---------------------------------------------
def test_nomes_de_arquivo_dos_exemplos_dos_pdfs(urls):
    assert urls.resultado(999999, 9999, "sp").endswith("/sp-c9999-e999999-u.json")  # instruções de download §5
    assert urls.resultado(999999, 3, "br").endswith("/br-c0003-e999999-u.json")  # EA20 (arquivo BR)
    assert urls.resultado(999999, 3, "sp").endswith("/sp-c0003-e999999-u.json")  # EA20 (arquivo UF)
    assert urls.resultado(999999, 3, "sp", municipio=71072).endswith("/sp71072-c0003-e999999-u.json")  # EA20 (município)
    assert urls.resultado(999999, 3, "sp", municipio=71072, zona=1).endswith("/sp71072-z0001-c0003-e999999-u.json")  # EA20 (zona)
    assert urls.municipios(12345).endswith("/mun-e012345-cm.json")  # EA12
    assert urls.acompanhamento(999999, "br").endswith("/br-e999999-ab.json")  # EA14
    assert urls.acompanhamento(999999, "sp").endswith("/sp-e999999-ab.json")  # EA15
    assert urls.eleitos(999999, 3, "br").endswith("/br-c0003-e999999-e.json")  # EA10
    assert urls.eleitos(999999, 11, "sp").endswith("/sp-c0011-e999999-e.json")  # EA10
    assert urls.config_secoes(12345, "mg").endswith("/mg-p012345-cs.json")  # EA16
    assert urls.auxiliar_secao(345, "sp", 7152, 1, 15).endswith("/p000345-sp-m07152-z0001-s0015-aux.json")  # EA18


# ---- URLs completas, as mesmas que responderam 200 no feed real em 03/10/2026 -------------------
def test_urls_completas_do_feed_real(urls):
    assert urls.config_eleicoes() == f"{B}/comum/config/ele-c.json"
    assert urls.municipios(6257) == f"{B}/ele2026/6257/config/mun-e006257-cm.json"
    assert urls.acompanhamento(6257, "br") == f"{B}/ele2026/6257/dados/br/br-e006257-ab.json"
    assert urls.resultado(6257, 1, "br") == f"{B}/ele2026/6257/dados/br/br-c0001-e006257-u.json"
    assert urls.resultado(6259, 6, "sp") == f"{B}/ele2026/6259/dados/sp/sp-c0006-e006259-u.json"
    assert urls.resultado(6257, 1, "sp", municipio=71072) == f"{B}/ele2026/6257/dados/sp/sp71072-c0001-e006257-u.json"
    assert urls.resultado(6257, 1, "zz") == f"{B}/ele2026/6257/dados/zz/zz-c0001-e006257-u.json"
    assert urls.foto(6257, "br", 280002551544) == f"{B}/ele2026/6257/fotos/br/280002551544.jpeg"


def test_diretorios_do_ea11_substituem_o_padrao():
    dirs = {"u": "<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados-novos/<uf>"}
    u = TseUrls("https://x.test/", "simulado", "ele2030", dirs)
    assert u.resultado(7, 1, "br") == "https://x.test/simulado/ele2030/7/dados-novos/br/br-c0001-e000007-u.json"


def test_como_jws_troca_apenas_a_extensao():
    assert como_jws(f"{B}/ele2026/6257/dados/br/br-c0001-e006257-u.json") == f"{B}/ele2026/6257/dados/br/br-c0001-e006257-u.jws"
    with pytest.raises(ValueError):
        como_jws("https://x.test/arquivo.jpeg")


# ---- validação das entradas (parte vem de parâmetros de rota) ----------------------------------
@pytest.mark.parametrize("uf", ["xx", "../etc", "sp/../br", "", "SP;", "bra"])
def test_uf_invalida_e_recusada(urls, uf):
    with pytest.raises(ValueError):
        urls.resultado(6257, 1, uf)


def test_br_nao_aceita_municipio_e_zona_exige_municipio(urls):
    with pytest.raises(ValueError):
        urls.resultado(6257, 1, "br", municipio=71072)
    with pytest.raises(ValueError):
        urls.resultado(6257, 1, "sp", zona=1)


@pytest.mark.parametrize("ruim", ["abc", "-1", "1e3", "12 34", "../1", "", "1234567"])
def test_numeros_invalidos_ou_grandes_demais_sao_recusados(urls, ruim):
    with pytest.raises(ValueError):
        urls.resultado(ruim, 1, "sp")  # eleição: no máximo 6 dígitos


@pytest.mark.parametrize("sq", ["../x", "12ab", "", "1" * 21, "28000/2"])
def test_sqcand_invalido_e_recusado(urls, sq):
    with pytest.raises(ValueError):
        urls.foto(6257, "br", sq)


def test_uf_e_normalizada_para_minuscula(urls):
    assert urls.resultado(6259, 3, "SP").endswith("/sp-c0003-e006259-u.json")
