"""Contagem de acessos ao painel (Diagnóstico): páginas, requisições, pessoas online, picos e o que NÃO é guardado."""
import json

import pytest

from app.acessos import JANELA_ONLINE_S, Acessos
from tests.conftest import montar_app


class Relogio:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def abrir(a, relogio, caminho="/api/v1/presidente", *, link=False, cliente="1.1.1.1|Chrome", avanca=0.0):
    relogio.t += avanca
    a.abrir(caminho, link, cliente)
    a.fechar(link)


def test_pessoas_online_so_dentro_da_janela_e_o_pico_fica_guardado():
    r = Relogio()
    a = Acessos(relogio=r)
    for i in range(3):
        abrir(a, r, cliente=f"10.0.0.{i}|Chrome", avanca=1.0)
    assert a.snapshot()["todos"]["online"] == 3
    # quem consulta de novo continua contando; quem sumiu sai depois da janela
    r.t += JANELA_ONLINE_S - 5
    abrir(a, r, cliente="10.0.0.0|Chrome")
    assert a.snapshot()["todos"]["online"] == 3
    r.t += 10
    s = a.snapshot()["todos"]
    assert s["online"] == 1 and s["pico_online"]["n"] == 3 and s["pico_online"]["em"]
    r.t += JANELA_ONLINE_S + 1
    s = a.snapshot()["todos"]
    assert s["online"] == 0 and s["pico_online"]["n"] == 3  # o pico não desce


def test_o_mesmo_aparelho_conta_uma_vez_mas_navegadores_diferentes_no_mesmo_ip_contam_separado():
    r = Relogio()
    a = Acessos(relogio=r)
    for _ in range(5):
        abrir(a, r, cliente="1.1.1.1|Chrome", avanca=1.0)
    abrir(a, r, cliente="1.1.1.1|Safari", avanca=1.0)
    s = a.snapshot()["todos"]
    assert s["online"] == 2 and s["requisicoes"] == 6


def test_link_publico_e_separado_do_acesso_local():
    r = Relogio()
    a = Acessos(relogio=r)
    abrir(a, r, link=True, cliente="203.0.113.7|Chrome", avanca=1.0)
    abrir(a, r, link=True, cliente="203.0.113.8|Safari", avanca=1.0)
    abrir(a, r, link=False, cliente="127.0.0.1|Chrome", avanca=1.0)
    a.pagina(True)
    a.pagina(False)
    s = a.snapshot()
    assert s["link"]["online"] == 2 and s["link"]["requisicoes"] == 2 and s["link"]["paginas"] == 1
    assert s["todos"]["online"] == 3 and s["todos"]["requisicoes"] == 3 and s["todos"]["paginas"] == 2


def test_arquivos_e_fotos_contam_como_requisicao_mas_nao_como_gente_online():
    r = Relogio()
    a = Acessos(relogio=r)
    abrir(a, r, "/static/css/app.css", cliente="9.9.9.9|X", avanca=1.0)
    abrir(a, r, "/foto/6257/br/123", cliente="9.9.9.9|X", avanca=1.0)
    s = a.snapshot()["todos"]
    assert s["requisicoes"] == 2 and s["online"] == 0


def test_requisicoes_por_minuto_agora_e_pico():
    r = Relogio()
    a = Acessos(relogio=r)
    for _ in range(30):
        abrir(a, r, avanca=1.0)  # 30 requisições em 30 s
    s = a.snapshot()["todos"]
    assert s["req_por_min"] == 30 and s["pico_req_por_min"]["n"] == 30
    r.t += 61
    s = a.snapshot()["todos"]
    assert s["req_por_min"] == 0 and s["pico_req_por_min"]["n"] == 30


def test_requisicoes_em_andamento_e_pico():
    r = Relogio()
    a = Acessos(relogio=r)
    for i in range(3):
        a.abrir("/api/v1/presidente", False, f"c{i}|x")
    a.fechar(False)
    s = a.snapshot()["todos"]
    assert s["em_andamento"] == 2 and s["pico_em_andamento"]["n"] == 3
    a.fechar(False)
    a.fechar(False)
    a.fechar(False)  # fechar a mais nunca deixa o contador negativo
    assert a.snapshot()["todos"]["em_andamento"] == 0


def test_totais_e_picos_sobrevivem_a_reinicio_mas_quem_esta_online_nao(tmp_path):
    arquivo = tmp_path / "acessos" / "oficial.json"
    r = Relogio()
    a = Acessos(arquivo, relogio=r)
    for i in range(4):
        abrir(a, r, link=True, cliente=f"5.5.5.{i}|x", avanca=1.0)
    a.pagina(True)
    a.salvar()
    b = Acessos(arquivo, relogio=Relogio(r.t + 500))
    s = b.snapshot()
    assert s["link"]["requisicoes"] == 4 and s["link"]["paginas"] == 1 and s["link"]["pico_online"]["n"] == 4
    assert s["link"]["online"] == 0 and s["desde"] == a.snapshot()["desde"]


def test_arquivo_ilegivel_recomeca_do_zero_sem_derrubar_nada(tmp_path):
    arquivo = tmp_path / "acessos.json"
    arquivo.write_text("{isso não é json", encoding="utf-8")
    a = Acessos(arquivo)
    assert a.snapshot()["todos"]["requisicoes"] == 0
    arquivo.write_text(json.dumps({"todos": {"paginas": "x"}, "link": {}}), encoding="utf-8")
    assert Acessos(arquivo).snapshot()["link"]["paginas"] == 0


def test_nenhum_ip_vai_para_o_disco_nem_para_a_resposta(tmp_path):
    arquivo = tmp_path / "acessos.json"
    r = Relogio()
    a = Acessos(arquivo, relogio=r)
    abrir(a, r, link=True, cliente="203.0.113.77|Mozilla/5.0 (iPhone)", avanca=1.0)
    a.salvar()
    texto = arquivo.read_text(encoding="utf-8") + json.dumps(a.snapshot())
    assert "203.0.113.77" not in texto and "Mozilla" not in texto and "iPhone" not in texto


# ---- integrado ao app --------------------------------------------------------------------------------
@pytest.fixture
def cliente(tmp_path):
    app, _, _ = montar_app(tmp_path, 0.5, cargos=(1, 3, 5))
    return app, app.test_client()


def test_so_paginas_html_bem_sucedidas_contam_como_visita(cliente):
    app, c = cliente
    acessos = app.extensions["acessos"]
    c.get("/")
    c.get("/uf/sp")
    c.get("/api/v1/meta")
    c.get("/uf/xx", headers={"Accept": "text/html"})  # 404: nem é visita
    s = acessos.snapshot()["todos"]
    assert s["paginas"] == 2 and s["requisicoes"] == 4 and s["online"] == 1
    assert acessos.snapshot()["link"]["requisicoes"] == 0  # nada chegou pelo link público


def test_diagnostico_e_healthz_nao_entram_na_conta(cliente):
    app, c = cliente
    for caminho in ("/status", "/api/v1/status", "/healthz"):
        assert c.get(caminho).status_code == 200
    assert app.extensions["acessos"].snapshot()["todos"]["requisicoes"] == 0


def test_cabecalho_da_cloudflare_marca_o_acesso_como_pelo_link_publico(cliente):
    app, c = cliente
    c.get("/", headers={"CF-Connecting-IP": "203.0.113.5", "User-Agent": "Celular"})
    c.get("/api/v1/presidente", headers={"CF-Connecting-IP": "203.0.113.5", "User-Agent": "Celular"})
    c.get("/", headers={"User-Agent": "Notebook"})
    s = app.extensions["acessos"].snapshot()
    assert s["link"]["paginas"] == 1 and s["link"]["requisicoes"] == 2 and s["link"]["online"] == 1
    assert s["todos"]["paginas"] == 2 and s["todos"]["requisicoes"] == 3 and s["todos"]["online"] == 2


def test_status_da_api_traz_os_acessos_e_o_arquivo_fica_na_pasta_de_dados(cliente, tmp_path):
    app, c = cliente
    c.get("/")
    d = c.get("/api/v1/status").get_json()
    assert set(d["acessos"]) == {"desde", "janela_online_s", "link", "todos"}
    assert set(d["acessos"]["todos"]) == {
        "paginas", "requisicoes", "online", "pico_online", "req_por_min", "pico_req_por_min", "em_andamento", "pico_em_andamento",
    }
    assert d["acessos"]["todos"]["paginas"] == 1 and d["acessos"]["janela_online_s"] == JANELA_ONLINE_S
    app.extensions["acessos"].salvar()
    assert (tmp_path / "acessos" / "oficial.json").exists()
