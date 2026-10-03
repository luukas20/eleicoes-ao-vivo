"""Testes de ponta a ponta: o painel real (poller + API + páginas) contra o simulador, num Chrome de verdade.

    python -m pytest -m e2e

Exige o pacote `playwright` e o Google Chrome instalado (usa o Chrome do sistema; não baixa navegador).
"""
import logging
import threading
import time
from types import SimpleNamespace

import pytest
from werkzeug.serving import make_server

from app import create_app
from app.config import Settings
from mock.gerador import Simulacao
from mock.server import criar_app

playwright_sync = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.e2e

INTERVALO = "intervalo=2000"  # o navegador consulta a cada 2 s (mínimo permitido)


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    logging.getLogger("werkzeug").setLevel(logging.ERROR)  # sem o log de cada requisição
    sim = Simulacao(duracao_s=100000.0, inicio=0.5)
    sim.pausar()
    simulador = make_server("127.0.0.1", 0, criar_app(sim), threaded=True)
    threading.Thread(target=simulador.serve_forever, daemon=True).start()
    cfg = Settings(
        tse_base=f"http://127.0.0.1:{simulador.server_port}", ambiente="simulado", escala_polling=0.05,
        max_rps=200, workers=6, desatualizado_apos_s=4, data_dir=tmp_path_factory.mktemp("dados"),
    )
    app = create_app(cfg)
    painel = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=painel.serve_forever, daemon=True).start()
    store = app.extensions["store"]
    limite = time.monotonic() + 30
    while time.monotonic() < limite and len(store.itens()) < 88:
        time.sleep(0.2)
    assert len(store.itens()) == 88, "o poller não carregou todos os arquivos do simulador"
    yield SimpleNamespace(sim=sim, url=f"http://127.0.0.1:{painel.server_port}", app=app)
    app.extensions["poller"].parar()
    painel.shutdown()
    simulador.shutdown()


@pytest.fixture(autouse=True)
def restaurar_simulacao(stack):
    yield
    stack.sim.ir_para(0.5)
    stack.sim.dv_presidente = True
    stack.sim.falha_status, stack.sim.falha_ate = None, 0.0


@pytest.fixture(scope="module")
def navegador():
    with playwright_sync.sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception as ex:  # sem Chrome instalado
            pytest.skip(f"Chrome indisponível para o Playwright: {ex}")
        yield browser
        browser.close()


@pytest.fixture
def abrir(navegador, stack):
    """Abre uma página do painel e devolve (page, mensagens_de_erro). Fecha o contexto no fim."""
    contextos = []

    def _abrir(caminho="/", *, largura=1280, altura=900, esquema="light", sep="?"):
        ctx = navegador.new_context(viewport={"width": largura, "height": altura}, color_scheme=esquema, locale="pt-BR", timezone_id="America/Sao_Paulo")
        contextos.append(ctx)
        page = ctx.new_page()
        erros: list[str] = []
        page.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: erros.append(f"requestfailed: {r.url}"))
        page.on("response", lambda r: erros.append(f"http {r.status}: {r.url}") if r.status >= 400 else None)
        page.goto(f"{stack.url}{caminho}{sep}{INTERVALO}", wait_until="networkidle")
        return page, erros

    yield _abrir
    for ctx in contextos:
        ctx.close()


def esperar(page, js, timeout=20000):
    """Espera a expressão JS ficar verdadeira.

    O polling é feito aqui, no Python, e não com `page.wait_for_function`: este usa `eval` no navegador
    em cada nova tentativa e a CSP do painel (script-src 'self') o proíbe — que é como deve ser.
    """
    fim = time.monotonic() + timeout / 1000
    while not page.evaluate(f"() => Boolean({js})"):
        if time.monotonic() > fim:
            raise AssertionError(f"tempo esgotado esperando: {js}\nURL: {page.url}\nTrecho da página: {page.inner_text('body')[:500]!r}")
        page.wait_for_timeout(150)


# ---- carregamento e estrutura ----------------------------------------------------------------------------
def test_painel_carrega_sem_erros_e_com_a_estrutura_esperada(abrir):
    page, erros = abrir("/")
    esperar(page, "document.querySelectorAll('.cand').length === 6")
    assert page.locator(".bloco").count() == 28  # 27 UFs + exterior
    assert page.locator(".kpi").count() == 5
    assert page.locator(".tabela tbody tr").count() == 28
    assert page.locator(".heroi-num").inner_text().replace("\n", "").endswith("%")
    assert "DADOS SIMULADOS" in page.locator("#faixa-simulado").inner_text() and page.locator("#faixa-simulado").is_visible()
    assert "Ao vivo" in page.locator("#chip-status").inner_text()
    assert erros == []


def test_as_barras_tem_a_mesma_escala_e_a_linha_de_50_aparece(abrir):
    page, _ = abrir("/")
    esperar(page, "document.querySelectorAll('.barra-trilho').length === 6")
    larguras = page.eval_on_selector_all(".barra-trilho", "els => els.map(e => Math.round(e.getBoundingClientRect().width))")
    assert len(set(larguras)) == 1 and larguras[0] > 150  # o trilho tem o mesmo comprimento em todas as linhas
    meta = page.locator(".barra-meta").first
    assert meta.is_visible()
    caixa_meta = meta.bounding_box()
    caixa_trilho = page.locator(".barra-trilho").first.bounding_box()
    assert abs((caixa_meta["x"] - caixa_trilho["x"]) - caixa_trilho["width"] / 2) < 3  # exatamente em 50%


def test_as_cores_do_mapa_batem_com_as_do_ranking_e_da_legenda(abrir):
    page, _ = abrir("/")
    esperar(page, "document.querySelectorAll('.legenda .chave[data-cor]').length >= 3")
    legenda = page.eval_on_selector_all(".legenda li", "els => els.map(e => e.textContent.trim())")
    assert any(t.startswith("ALFA") for t in legenda) and "Outros candidatos" in legenda
    cores_ranking = page.eval_on_selector_all(".cand", "els => els.map(e => e.querySelector('.barra-preench').dataset.cor)")
    assert cores_ranking[:3] == ["1", "2", "3"] and set(cores_ranking[3:]) == {"0"}
    cores_mapa = set(page.eval_on_selector_all(".bloco[data-cor]", "els => els.map(e => e.dataset.cor)"))
    assert cores_mapa <= {"0", "1", "2", "3"} and {"1", "2"} <= cores_mapa


# ---- interação -------------------------------------------------------------------------------------------
def test_dica_aparece_no_hover_e_no_foco_do_teclado(abrir):
    page, _ = abrir("/")
    esperar(page, "document.querySelectorAll('.cand').length === 6")
    assert page.locator("#dica").is_hidden()
    page.locator(".cand").first.hover()
    assert page.locator("#dica").is_visible() and "ALFA" in page.locator("#dica").inner_text()
    page.mouse.move(5, 5)
    assert page.locator("#dica").is_hidden()
    page.locator(".cand").nth(1).focus()  # mesmo conteúdo no foco por teclado
    assert page.locator("#dica").is_visible() and "BETA" in page.locator("#dica").inner_text()
    page.keyboard.press("Escape")
    assert page.locator("#dica").is_hidden()


def test_clicar_num_bloco_do_mapa_abre_a_pagina_da_uf(abrir):
    page, _ = abrir("/")
    esperar(page, "document.querySelectorAll('.bloco[data-cor]').length > 5")
    page.locator("a.bloco.uf-sp").click()
    page.wait_for_url("**/uf/sp**")
    esperar(page, "document.querySelectorAll('.cand').length > 0")
    assert page.locator(".uf-titulo").inner_text() == "São Paulo"


def test_tema_escuro_alterna_e_persiste_entre_visitas(abrir):
    page, _ = abrir("/")
    esperar(page, "document.querySelectorAll('.cand').length === 6")
    assert page.evaluate("document.documentElement.getAttribute('data-tema')") is None
    page.locator("#btn-tema").click()
    assert page.evaluate("document.documentElement.getAttribute('data-tema')") == "escuro"
    fundo_escuro = page.evaluate("getComputedStyle(document.body).backgroundColor")
    page.reload(wait_until="networkidle")
    assert page.evaluate("document.documentElement.getAttribute('data-tema')") == "escuro"  # lembrou
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == fundo_escuro == "rgb(13, 13, 13)"
    page.locator("#btn-tema").click()
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(249, 249, 247)"


def test_tabela_de_ufs_ordena_pelo_cabecalho(abrir):
    page, _ = abrir("/")
    esperar(page, "document.querySelectorAll('.tabela tbody tr').length === 28")
    primeira = lambda: page.locator(".tabela tbody tr").first.locator("td").first.inner_text()
    assert primeira() == "Acre"
    page.get_by_role("button", name="Totalizado").click()  # decrescente
    totais = page.eval_on_selector_all(".tabela tbody tr", "els => els.map(e => parseFloat(e.cells[1].textContent.replace(',', '.')))")
    assert totais == sorted(totais, reverse=True)
    page.get_by_role("button", name="Totalizado").click()  # crescente
    totais = page.eval_on_selector_all(".tabela tbody tr", "els => els.map(e => parseFloat(e.cells[1].textContent.replace(',', '.')))")
    assert totais == sorted(totais)


# ---- páginas de UF e de cargos ----------------------------------------------------------------------------
def test_pagina_da_uf_troca_de_disputa_pelas_abas(abrir):
    page, erros = abrir("/uf/sp")
    esperar(page, "document.querySelectorAll('[role=tab]').length === 3")
    assert [b.inner_text() for b in page.locator("[role=tab]").all()] == ["Presidente", "Governador", "Senador"]
    assert page.locator("#painel-presidente").is_visible() and page.locator("#painel-senador").is_hidden()
    page.get_by_role("tab", name="Senador").click()
    assert page.locator("#painel-senador").is_visible() and page.locator("#painel-presidente").is_hidden()
    assert page.locator("#painel-senador .cand").count() == 5
    assert page.locator("#painel-senador .corte").inner_text() == "2 vagas"  # linha de corte do Senado
    assert page.locator("#painel-senador .barra-meta").count() == 0  # sem linha de 50% no Senado
    assert page.locator("#painel-governador .barra-meta").count() == 4
    assert "#senador" in page.url
    assert erros == []


def test_tabela_do_senado_nao_usa_cor_de_identidade_e_mede_a_diferenca_certa(abrir):
    page, _ = abrir("/senadores")
    esperar(page, "document.querySelectorAll('.tabela tbody tr').length === 27")
    assert page.locator(".tabela .chave").count() == 0  # nenhuma cor: o candidato muda de UF para UF
    cab = page.eval_on_selector_all(".tabela th", "els => els.map(e => e.textContent.trim())")
    assert cab[:3] == ["UF ▲", "Totalizado", "1º colocado"] and "3º colocado (fora das vagas)" in cab
    assert "(" in page.locator(".tabela tbody tr").first.locator("td").nth(2).inner_text()  # nome (PARTIDO)
    ajuda = page.get_by_role("columnheader", name="Diferença").get_attribute("title")
    assert "2º colocado (última vaga)" in ajuda and "3º (primeiro fora das vagas)" in ajuda


def test_navegacao_entre_cargos_marca_a_aba_ativa(abrir):
    page, _ = abrir("/")
    page.get_by_role("link", name="Governadores").click()
    page.wait_for_url("**/governadores**")
    assert page.locator(".aba[aria-current=page]").inner_text() == "Governadores"
    esperar(page, "document.querySelectorAll('.tabela tbody tr').length === 27")
    assert "UFs com apuração iniciada" in page.locator("#resumo").inner_text()


# ---- estados da apuração ----------------------------------------------------------------------------------
def test_antes_da_apuracao_mostra_aviso_e_nenhum_numero_inventado(abrir, stack):
    stack.sim.ir_para(0.0)
    page, _ = abrir("/")
    esperar(page, "document.querySelector('.aviso') && document.querySelector('.aviso').textContent.includes('ainda não iniciada')")
    assert page.locator(".heroi-num").inner_text().startswith("0,00")
    assert page.locator(".cand-pct").first.inner_text() == "—"  # sem "0,00%" para quem nem começou
    assert page.locator(".kpi-valor").nth(1).inner_text() == "—"  # comparecimento


def test_votacao_do_presidente_nao_liberada(abrir, stack):
    stack.sim.dv_presidente = False
    page, _ = abrir("/")
    esperar(page, "document.querySelector('.aviso') && document.querySelector('.aviso').textContent.includes('não liberada')")
    assert page.locator(".cand-pct").first.inner_text() == "—"
    assert "17h" in page.locator(".aviso").first.inner_text()
    assert page.locator(".heroi-num").inner_text() != "0,00%"  # seções já aparecem; só os votos ficam zerados


def test_final_da_apuracao_mostra_totalizacao_concluida_e_segundo_turno(abrir, stack):
    stack.sim.ir_para(1.0)
    page, _ = abrir("/")
    esperar(page, "document.body.textContent.includes('Totalização final concluída')")
    assert page.locator(".heroi-num").inner_text().startswith("100,00")
    selos = page.eval_on_selector_all(".selo:not([hidden])", "els => els.map(e => e.textContent.trim())")
    assert selos and all(s in ("Eleito", "2º turno") for s in selos)
    esperar(page, "[...document.querySelectorAll('.tabela tbody tr')].every(r => r.cells[1].textContent.includes('100,00'))")


def test_aviso_de_dado_desatualizado_e_recuperacao(abrir, stack):
    page, _ = abrir("/")
    esperar(page, "document.querySelector('#chip-status').textContent.includes('Ao vivo')")
    stack.sim.falha_status, stack.sim.falha_ate = 503, time.monotonic() + 60  # o TSE "cai"
    esperar(page, "document.querySelector('#chip-status').textContent.includes('Sem atualização do TSE')", timeout=30000)
    assert page.locator("#chip-status").get_attribute("data-estado") == "grave"
    assert page.locator(".cand").count() == 6  # continua mostrando o último dado recebido
    stack.sim.falha_status, stack.sim.falha_ate = None, 0.0  # o TSE volta
    esperar(page, "document.querySelector('#chip-status').textContent.includes('Ao vivo')", timeout=30000)


# ---- acessibilidade (axe-core) -------------------------------------------------------------------------------
@pytest.mark.parametrize("esquema", ["light", "dark"])
@pytest.mark.parametrize("progresso, inicio_do_heroi", [(0.0, "0,00"), (0.5, ""), (1.0, "100,00")])
def test_acessibilidade_sem_violacoes_do_axe(navegador, stack, esquema, progresso, inicio_do_heroi):
    """Contraste, nomes acessíveis, estrutura: apuração vazia, no meio e final, nos dois temas."""
    axe_pw = pytest.importorskip("axe_playwright_python.sync_playwright")
    stack.sim.ir_para(progresso)
    # bypass_csp só aqui, para o axe injetar o próprio script; as outras checagens rodam com a CSP estrita
    ctx = navegador.new_context(viewport={"width": 1280, "height": 900}, color_scheme=esquema, locale="pt-BR", bypass_csp=True)
    try:
        page = ctx.new_page()
        axe = axe_pw.Axe()
        paginas = [
            (f"/?{INTERVALO}", ".cand"),
            (f"/uf/sp?{INTERVALO}#governador", "#painel-governador .cand"),
            (f"/governadores?{INTERVALO}", ".tabela tbody tr"),
            (f"/senadores?{INTERVALO}", ".tabela tbody tr"),
        ]
        for caminho, pronto in paginas:
            page.goto(f"{stack.url}{caminho}", wait_until="networkidle")
            esperar(page, f"document.querySelectorAll('{pronto}').length > 0")
            if caminho.startswith("/?"):
                esperar(page, f"document.querySelector('.heroi-num').textContent.startsWith('{inicio_do_heroi}')")
                page.wait_for_timeout(2500)  # a tabela e o mapa (arquivos por UF) chegam depois do total nacional
            page.wait_for_timeout(1200)
            violacoes = axe.run(page).response["violations"]
            resumo = [
                f"{v['id']} [{v['impact']}] {v['help']}: " + "; ".join(f"{n['target']} {n['failureSummary'].splitlines()[-1].strip()}" for n in v["nodes"][:3])
                for v in violacoes
            ]
            assert not violacoes, f"{esquema} {caminho} @{progresso}:\n" + "\n".join(resumo)
    finally:
        ctx.close()


# ---- celular ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("caminho", ["/", "/uf/sp", "/senadores"])
def test_no_celular_a_pagina_nao_rola_na_horizontal(abrir, caminho):
    page, erros = abrir(caminho, largura=390, altura=844)
    esperar(page, "document.querySelectorAll('.cand, .tabela tbody tr').length > 3")
    page.wait_for_timeout(1000)
    sobra = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert sobra <= 0, f"a página tem {sobra}px de rolagem horizontal"
    assert erros == []


def test_no_celular_a_coluna_diferenca_cabe_na_tela(abrir):
    page, _ = abrir("/", largura=390, altura=844)
    esperar(page, "document.querySelectorAll('.tabela tbody tr').length === 28")
    cab = page.get_by_role("columnheader", name="Diferença").bounding_box()
    assert cab["x"] + cab["width"] <= 390
