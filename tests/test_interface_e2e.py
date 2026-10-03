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
from app.tse.dominio import UF_NOMES, UFS
from mock.gerador import Simulacao
from mock.server import criar_app
from tools.gerar_mapa import sem_acento

playwright_sync = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.e2e

INTERVALO = "intervalo=2000"  # o navegador consulta a cada 2 s (mínimo permitido)


def montar_stack(tmp_path_factory, inicio):
    """Sobe um simulador (parado em `inicio`) e um painel real consultando esse simulador."""
    logging.getLogger("werkzeug").setLevel(logging.ERROR)  # sem o log de cada requisição
    sim = Simulacao(duracao_s=100000.0, inicio=inicio)
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
    pilha = SimpleNamespace(sim=sim, url=f"http://127.0.0.1:{painel.server_port}", app=app)

    def encerrar():
        app.extensions["poller"].parar()
        painel.shutdown()
        simulador.shutdown()

    return pilha, encerrar


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    pilha, encerrar = montar_stack(tmp_path_factory, 0.5)
    yield pilha
    encerrar()


@pytest.fixture(scope="module")
def stack_grafico(tmp_path_factory):
    """Pilha à parte, com histórico próprio: o gráfico depende de uma sequência de totalizações."""
    pilha, encerrar = montar_stack(tmp_path_factory, 0.0)
    yield pilha
    encerrar()


@pytest.fixture(autouse=True)
def restaurar_simulacao(stack):
    yield
    stack.sim.ir_para(0.5)
    stack.sim.dv_presidente = True
    stack.sim.falha_status, stack.sim.falha_ate = None, 0.0


def avancar_apuracao(pilha, passos, espera=1.4):
    """Leva a apuração simulada por `passos` (frações de 0 a 1); cada passo gera um ponto novo no histórico."""
    for x in passos:
        pilha.sim.ir_para(x)
        time.sleep(espera)  # o poller (escala 0,05) consulta o arquivo nacional a cada ~1 s


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

    def _abrir(caminho="/", *, largura=1280, altura=900, esquema="light", sep="?", pilha=None, toque=False):
        alvo = pilha or stack
        ctx = navegador.new_context(
            viewport={"width": largura, "height": altura}, color_scheme=esquema, locale="pt-BR", timezone_id="America/Sao_Paulo",
            is_mobile=toque, has_touch=toque, device_scale_factor=2 if toque else 1,
        )
        contextos.append(ctx)
        page = ctx.new_page()
        erros: list[str] = []
        page.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: erros.append(f"requestfailed: {r.url}"))
        page.on("response", lambda r: erros.append(f"http {r.status}: {r.url}") if r.status >= 400 else None)
        page.goto(f"{alvo.url}{caminho}{sep}{INTERVALO}", wait_until="networkidle")
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


def esperar_mapa(page):
    """O desenho do mapa é um arquivo à parte: espera as 27 UFs desenhadas e pintadas com a cor de quem lidera."""
    esperar(page, "document.querySelectorAll('a.uf').length === 27 && document.querySelectorAll('a.uf[data-cor]').length > 10")


def centro_da_sigla(page, uf):
    """Centro (na janela) da sigla desenhada dentro do estado; a sigla não captura o mouse, então o ponto cai sobre o estado."""
    sigla = page.locator(f".uf-rotulo:text-is('{uf.upper()}')")
    sigla.scroll_into_view_if_needed()  # o mapa fica abaixo da dobra e o mouse do Playwright não rola a página sozinho
    caixa = sigla.bounding_box()
    return caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2


# ---- carregamento e estrutura ----------------------------------------------------------------------------
def test_painel_carrega_sem_erros_e_com_a_estrutura_esperada(abrir):
    page, erros = abrir("/")
    esperar(page, "document.querySelectorAll('.cand').length === 6")
    assert page.locator(".bloco").count() == 28  # 27 UFs + exterior (a visão de blocos fica no DOM, escondida)
    esperar_mapa(page)
    assert page.locator("a.uf").count() == 27 and page.locator(".chip-exterior").count() == 1
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


def test_clicar_num_estado_do_mapa_abre_a_pagina_da_uf(abrir):
    page, _ = abrir("/")
    esperar_mapa(page)
    page.mouse.click(*centro_da_sigla(page, "sp"))
    page.wait_for_url("**/uf/sp**")
    esperar(page, "document.querySelectorAll('.cand').length > 0")
    assert page.locator(".uf-titulo").inner_text() == "São Paulo"


def test_clicar_na_etiqueta_de_um_estado_pequeno_abre_a_pagina_da_uf(abrir):
    page, _ = abrir("/")
    esperar_mapa(page)
    etiqueta = page.locator("a.chip-uf:not([data-oculto])", has_text="RN")
    assert etiqueta.count() == 1  # o Rio Grande do Norte é pequeno demais para a sigla caber dentro dele
    etiqueta.click()
    page.wait_for_url("**/uf/rn**")


# ---- mapa geográfico -------------------------------------------------------------------------------------------
def test_mapa_pinta_cada_uf_com_a_cor_de_quem_lidera_igual_aos_blocos_e_a_legenda(abrir):
    page, erros = abrir("/")
    esperar_mapa(page)
    assert page.locator(".mapa-geo").is_visible() and page.locator(".mapa").is_hidden()  # o mapa é a visão padrão
    mapa = page.evaluate("Object.fromEntries([...document.querySelectorAll('a.uf')].map(a => [a.dataset.uf, a.dataset.cor]))")
    blocos = page.evaluate("Object.fromEntries([...document.querySelectorAll('.bloco')].map(b => [b.dataset.uf, b.dataset.cor]))")
    assert len(mapa) == 27 and mapa == {uf: blocos[uf] for uf in mapa}
    assert set(mapa.values()) <= {"0", "1", "2", "3"} and {"1", "2"} <= set(mapa.values())
    assert page.locator(".chip-exterior").get_attribute("data-cor") == blocos["zz"]
    cor_do_estado = page.evaluate("getComputedStyle(document.querySelector('a.uf[data-uf=sp] path')).fill")
    cor_da_legenda = page.evaluate(
        "cor => getComputedStyle(document.querySelector(`.legenda .chave[data-cor='${cor}']`)).backgroundColor", mapa["sp"])
    assert cor_do_estado == cor_da_legenda  # a mesma cor da pessoa, no mapa e na legenda
    assert erros == []  # inclui violações da CSP


def test_mapa_sem_votos_liberados_fica_neutro_e_nao_inventa_lider(abrir, stack):
    stack.sim.dv_presidente = False  # as seções já são totalizadas, mas o TSE ainda não liberou os votos do Presidente
    page, _ = abrir("/")
    # os arquivos por UF chegam depois do nacional (e mais devagar quando nada mudava): espera o estado, não um tempo fixo
    esperar(page, "document.querySelectorAll('a.uf').length === 27 && document.querySelectorAll('a.uf[data-cor]').length === 0", timeout=40000)
    esperar(page, "!document.querySelector('.chip-exterior').hasAttribute('data-cor')", timeout=40000)
    assert "sem votos liberados" in page.locator("a.uf[data-uf=sp]").get_attribute("aria-label")
    fundo = page.evaluate("getComputedStyle(document.querySelector('a.uf[data-uf=sp] path')).fill")
    assert fundo == page.evaluate("getComputedStyle(document.querySelector('.chave-vazia')).backgroundColor")  # igual à legenda


def test_mapa_dica_e_contorno_no_mouse_e_no_teclado(abrir):
    page, _ = abrir("/")
    esperar_mapa(page)
    assert page.locator("#dica").is_hidden() and page.locator(".uf-destaque").get_attribute("d") is None
    page.mouse.move(*centro_da_sigla(page, "sp"))
    assert page.locator("#dica").is_visible() and "São Paulo" in page.locator("#dica").inner_text()
    assert page.locator(".uf-destaque").get_attribute("d") == page.locator("a.uf[data-uf=sp] path").get_attribute("d")
    page.mouse.move(2, 2)
    assert page.locator("#dica").is_hidden() and page.locator(".uf-destaque").get_attribute("d") is None
    page.locator("a.uf[data-uf=ba]").focus()  # mesmo conteúdo e mesmo contorno no foco por teclado
    assert page.locator("#dica").is_visible() and "Bahia" in page.locator("#dica").inner_text()
    assert page.locator(".uf-destaque").get_attribute("d") == page.locator("a.uf[data-uf=ba] path").get_attribute("d")
    page.keyboard.press("Escape")
    assert page.locator("#dica").is_hidden()


def test_mapa_tab_percorre_as_ufs_em_ordem_alfabetica_do_nome(abrir):
    page, _ = abrir("/")
    esperar_mapa(page)
    ordem_no_dom = page.eval_on_selector_all("a.uf", "els => els.map(e => e.dataset.uf)")
    assert ordem_no_dom == sorted(UFS, key=lambda uf: sem_acento(UF_NOMES[uf]))
    page.locator("a.uf[data-uf=ac]").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.dataset.uf") == "al"  # Acre -> Alagoas
    assert page.locator("a.chip-uf").first.get_attribute("tabindex") == "-1"  # as etiquetas repetem o link: não entram no Tab


def test_alternar_entre_mapa_e_blocos_e_lembrar_a_escolha(abrir):
    page, _ = abrir("/")
    esperar_mapa(page)
    page.get_by_role("button", name="Blocos", exact=True).click()
    assert page.locator(".mapa").is_visible() and page.locator(".mapa-geo").is_hidden()
    assert page.get_by_role("button", name="Blocos", exact=True).get_attribute("aria-pressed") == "true"
    assert page.get_by_role("button", name="Mapa", exact=True).get_attribute("aria-pressed") == "false"
    page.reload(wait_until="networkidle")
    esperar(page, "document.querySelectorAll('.bloco[data-cor]').length > 10")
    assert page.locator(".mapa").is_visible() and page.locator(".mapa-geo").is_hidden()  # lembrou a escolha
    page.locator(".bloco.uf-sp").click()  # os blocos continuam clicáveis
    page.wait_for_url("**/uf/sp**")
    page.go_back(wait_until="networkidle")
    page.get_by_role("button", name="Mapa", exact=True).click()
    esperar(page, "[...document.querySelectorAll('.uf-rotulo')].some(t => !t.hasAttribute('data-oculto'))")  # o layout é refeito ao reexibir
    assert page.locator(".mapa-geo").is_visible()


def test_sem_o_desenho_do_mapa_mostra_os_blocos(navegador, stack):
    ctx = navegador.new_context(viewport={"width": 1280, "height": 900}, locale="pt-BR")
    try:
        page = ctx.new_page()
        page.route("**/mapa-ufs.json", lambda rota: rota.fulfill(status=404, body="não achei"))
        page.goto(f"{stack.url}/?{INTERVALO}", wait_until="networkidle")
        esperar(page, "document.querySelectorAll('.bloco[data-cor]').length > 10")
        assert page.locator(".mapa").is_visible()
        assert page.locator("[aria-label='Forma de exibir as UFs']").is_hidden()  # sem o desenho não há o que escolher
    finally:
        ctx.close()


CONFERE_MAPA = """() => {
  const problemas = [];
  const visiveis = (sel) => [...document.querySelectorAll(sel)].filter((e) => !e.hasAttribute('data-oculto'));
  const caixa = (e) => e.getBoundingClientRect();
  const area = document.querySelector('.mapa-geo-svg').getBoundingClientRect();
  const rotulos = visiveis('.uf-rotulo');
  for (const t of rotulos) {   // a sigla está mesmo sobre o próprio estado: centro e as duas pontas
    const uf = t.textContent.toLowerCase();
    const r = caixa(t);
    for (const x of [r.left + 1, r.left + r.width / 2, r.right - 1]) {
      const forma = document.elementsFromPoint(x, r.top + r.height / 2).find((e) => e.classList.contains('uf-forma'));
      if (!forma || forma.parentNode.dataset.uf !== uf) problemas.push(`a sigla ${uf} sai do estado`);
    }
  }
  const etiquetas = visiveis('.chip-uf').map((c) => ({ nome: c.textContent.trim(), r: caixa(c.querySelector('rect')) }));
  const bate = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  etiquetas.forEach((e, i) => {
    if (e.r.left < area.left - 1 || e.r.right > area.right + 1 || e.r.top < area.top - 1 || e.r.bottom > area.bottom + 1) problemas.push(`a etiqueta ${e.nome} sai do mapa`);
    etiquetas.slice(i + 1).forEach((o) => { if (bate(e.r, o.r)) problemas.push(`as etiquetas ${e.nome} e ${o.nome} se sobrepõem`); });
    rotulos.forEach((t) => { if (bate(e.r, caixa(t))) problemas.push(`a etiqueta ${e.nome} cobre a sigla ${t.textContent}`); });
  });
  const identificadas = new Set([...rotulos.map((t) => t.textContent.toLowerCase()), ...etiquetas.map((e) => e.nome.toLowerCase())]);
  return {
    problemas, sem_identificacao: [...document.querySelectorAll('a.uf')].map((a) => a.dataset.uf).filter((u) => !identificadas.has(u)),
    altura_das_etiquetas: etiquetas.length ? Math.min(...etiquetas.map((e) => e.r.height)) : 0,
  };
}"""


@pytest.mark.parametrize("largura, toque", [(360, True), (390, True), (600, True), (768, True), (820, True), (1024, True), (1280, False), (1600, False)])
def test_mapa_siglas_dentro_dos_estados_e_etiquetas_sem_se_atropelar(abrir, largura, toque):
    # janela bem alta: `elementsFromPoint` só enxerga o que está dentro da janela e o mapa fica abaixo da dobra
    page, erros = abrir("/", largura=largura, altura=2600, toque=toque)
    esperar_mapa(page)
    page.wait_for_timeout(700)
    r = page.evaluate(CONFERE_MAPA)
    assert r["problemas"] == [], f"{largura}px: {r['problemas']}"
    if largura >= 390:
        assert r["sem_identificacao"] == [], r  # toda UF tem a sigla dentro ou uma etiqueta ao lado
    else:
        assert len(r["sem_identificacao"]) <= 2, r  # só telas muito estreitas perdem algumas siglas
    assert r["altura_das_etiquetas"] >= (24 if toque else 18)  # alvo de toque mínimo do WCAG 2.2 (24 px) nas etiquetas
    assert erros == []


def test_mapa_acompanha_a_apuracao_ate_o_fim(abrir, stack):
    page, _ = abrir("/")
    esperar_mapa(page)
    stack.sim.ir_para(1.0)
    esperar(page, "document.body.textContent.includes('Totalização final concluída')")
    esperar(page, "[...document.querySelectorAll('a.uf')].every(a => a.getAttribute('aria-label').includes('100,00%'))", timeout=30000)
    mapa = page.evaluate("Object.fromEntries([...document.querySelectorAll('a.uf')].map(a => [a.dataset.uf, a.dataset.cor]))")
    blocos = page.evaluate("Object.fromEntries([...document.querySelectorAll('.bloco')].map(b => [b.dataset.uf, b.dataset.cor]))")
    assert mapa == {uf: blocos[uf] for uf in mapa} and len(mapa) == 27


def test_clicar_num_bloco_abre_a_pagina_da_uf(abrir):
    page, _ = abrir("/")
    page.get_by_role("button", name="Blocos", exact=True).click()
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


def test_busca_de_municipio_leva_a_pagina_com_dados_consultados_sob_demanda(abrir):
    page, erros = abrir("/uf/sp")
    esperar(page, "document.querySelectorAll('[role=tab]').length === 3")
    page.fill("#busca-mun", "capital")
    esperar(page, "document.querySelectorAll('#res-mun li').length >= 1")
    assert "SÃO PAULO" in page.locator("#res-mun a").first.inner_text()
    assert page.locator("#aviso-busca").inner_text().endswith("encontrado(s).")
    page.locator("#res-mun a").first.click()
    page.wait_for_url("**/municipio/sp/**")
    # o servidor só começa a consultar o TSE para este município agora; os dados chegam em segundos
    esperar(page, "document.querySelectorAll('.cand').length > 0", timeout=30000)
    assert "SÃO PAULO" in page.locator("#titulo-municipio").inner_text()
    assert [b.inner_text() for b in page.locator("[role=tab]").all()] == ["Presidente", "Governador", "Senador"]
    assert page.locator(".migalhas a").inner_text() == "São Paulo"
    assert "SÃO PAULO" in page.title()
    esperar(page, "document.querySelector('.heroi-num').textContent.trim() !== ''")
    page.get_by_role("tab", name="Senador").click()
    assert page.locator("#painel-senador .cand").count() == 5 and page.locator("#painel-senador .corte").inner_text() == "2 vagas"
    assert erros == []


def test_municipio_inexistente_mostra_aviso_sem_ficar_repetindo(abrir, stack):
    page, _ = abrir("/municipio/sp/99999")
    esperar(page, "document.querySelector('.aviso') && document.querySelector('.aviso').textContent.includes('não encontrado')")
    assert page.locator(".aviso").inner_text().startswith("Município indisponível.")
    antes = len([k for k, e in stack.app.extensions["poller"]._estados.items() if e.expira_em is not None])
    page.wait_for_timeout(3500)
    assert len([k for k, e in stack.app.extensions["poller"]._estados.items() if e.expira_em is not None]) == antes  # nada novo no poller


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
            (f"/municipio/sp/{Simulacao.codigo_municipio('sp', 0):05d}?{INTERVALO}", ".cand"),
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


@pytest.mark.parametrize("esquema", ["light", "dark"])
@pytest.mark.parametrize("progresso", [0.0, 0.5])
def test_acessibilidade_da_visao_em_blocos(navegador, stack, esquema, progresso):
    axe_pw = pytest.importorskip("axe_playwright_python.sync_playwright")
    stack.sim.ir_para(progresso)
    ctx = navegador.new_context(viewport={"width": 1280, "height": 900}, color_scheme=esquema, locale="pt-BR", bypass_csp=True)
    try:
        ctx.add_init_script("try { localStorage.setItem('mapa-visao', 'blocos'); } catch (e) {}")
        page = ctx.new_page()
        page.goto(f"{stack.url}/?{INTERVALO}", wait_until="networkidle")
        esperar(page, "document.querySelectorAll('.cand').length > 0 && document.querySelector('.mapa').offsetParent !== null")
        page.wait_for_timeout(3000)
        violacoes = axe_pw.Axe().run(page).response["violations"]
        resumo = [f"{v['id']} [{v['impact']}] {v['help']}: " + "; ".join(str(n['target']) for n in v["nodes"][:3]) for v in violacoes]
        assert not violacoes, "\n".join(resumo)
    finally:
        ctx.close()


# ---- gráfico de evolução ----------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def grafico_pronto(stack_grafico):
    """Pilha com histórico suficiente (≥ 6 totalizações) para o gráfico desenhar linhas."""
    historico = stack_grafico.app.extensions["servico"].historico
    if len(historico.serie("u:6257:1:br")) < 6:
        avancar_apuracao(stack_grafico, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
    return stack_grafico


def test_grafico_ciclo_de_vida_vazio_um_ponto_e_linhas(abrir, stack_grafico):
    page, erros = abrir("/", pilha=stack_grafico)
    esperar(page, "document.querySelector('.grafico .vazio') && !document.querySelector('.grafico .vazio').hidden")
    assert "primeiras urnas" in page.locator(".grafico .vazio").inner_text()  # nada apurado: só explica
    assert page.locator(".grafico svg").count() == 0
    avancar_apuracao(stack_grafico, [0.2])
    esperar(page, "document.querySelector('.grafico .vazio').textContent.includes('segunda atualização')", timeout=30000)
    avancar_apuracao(stack_grafico, [0.3, 0.4, 0.5])
    esperar(page, "document.querySelectorAll('.grafico svg path.serie').length === 3", timeout=40000)
    assert page.locator(".grafico .vazio").is_hidden()
    assert erros == []


def test_grafico_mostra_tres_linhas_legenda_pontas_e_cores_do_ranking(abrir, grafico_pronto):
    page, erros = abrir("/", pilha=grafico_pronto)
    esperar(page, "document.querySelectorAll('.grafico svg path.serie').length === 3")
    assert page.locator(".grafico .ponto-final").count() == 3
    legenda = page.eval_on_selector_all(".grafico .legenda-linhas li", "els => els.map(e => e.textContent.trim())")
    assert len(legenda) == 3 and legenda[0].startswith("ALFA") and "%" in legenda[0]
    cores_linhas = page.eval_on_selector_all(".grafico path.serie", "els => els.map(e => e.dataset.cor)")
    cores_ranking = page.eval_on_selector_all(".cand", "els => els.slice(0, 3).map(e => e.querySelector('.barra-preench').dataset.cor)")
    assert cores_linhas == cores_ranking == ["1", "2", "3"]  # a mesma cor da pessoa no ranking, no mapa e no gráfico
    assert page.locator(".grafico .rotulo-fim").count() == 3  # tela larga: rótulos diretos nas pontas
    eixo_y = page.eval_on_selector_all(".grafico .grade .eixo-txt", "els => els.map(e => e.textContent)")
    assert eixo_y and all(t.endswith("%") and int(t[:-1]) % 5 == 0 for t in eixo_y)  # números redondos nas duas pontas do eixo
    assert page.locator(".grafico svg").get_attribute("aria-label").startswith("Evolução do percentual dos votos desde")
    assert page.locator(".grafico-area").get_attribute("tabindex") == "0"  # alcançável pelo teclado
    assert erros == []


def test_grafico_hover_mostra_dica_com_as_tres_linhas_e_mira(abrir, grafico_pronto):
    page, _ = abrir("/", pilha=grafico_pronto)
    esperar(page, "document.querySelectorAll('.grafico svg path.serie').length === 3")
    page.locator(".grafico").scroll_into_view_if_needed()
    caixa = page.locator(".grafico .captura").bounding_box()
    page.mouse.move(caixa["x"] + caixa["width"] * 0.5, caixa["y"] + caixa["height"] * 0.5)
    assert page.locator("#dica").is_visible()
    assert page.locator("#dica .dica-linha").count() == 3 and "das seções" in page.locator("#dica .dica-titulo").inner_text()
    assert page.locator("#dica .dica-linha b").first.inner_text().endswith("%")  # o valor lidera; o nome vem depois
    assert page.locator(".grafico .mira").get_attribute("visibility") == "visible"
    assert page.locator(".grafico .ponto-mira[visibility=visible]").count() == 3
    page.mouse.move(5, 5)
    assert page.locator("#dica").is_hidden() and page.locator(".grafico .mira").get_attribute("visibility") == "hidden"


def test_grafico_teclado_percorre_os_momentos(abrir, grafico_pronto):
    page, _ = abrir("/", pilha=grafico_pronto)
    esperar(page, "document.querySelectorAll('.grafico svg path.serie').length === 3")
    page.locator(".grafico-area").focus()
    page.keyboard.press("End")
    ultimo = page.locator("#dica .dica-titulo").inner_text()
    page.keyboard.press("Home")
    primeiro = page.locator("#dica .dica-titulo").inner_text()
    assert page.locator("#dica").is_visible() and primeiro != ultimo
    page.keyboard.press("ArrowRight")
    assert page.locator("#dica .dica-titulo").inner_text() != primeiro
    page.keyboard.press("Escape")
    assert page.locator("#dica").is_hidden()


def test_grafico_alterna_eixo_e_tabela_equivalente(abrir, grafico_pronto):
    page, _ = abrir("/", pilha=grafico_pronto)
    esperar(page, "document.querySelectorAll('.grafico svg path.serie').length === 3")
    horas = page.eval_on_selector_all(".grafico .eixo-x text", "els => els.map(e => e.textContent)")
    assert horas and all(":" in t for t in horas)  # eixo de horário
    page.get_by_role("button", name="% das seções").click()
    secoes = page.eval_on_selector_all(".grafico .eixo-x text", "els => els.map(e => e.textContent)")
    assert secoes[0] == "0%" and secoes[-1] == "100%"
    pontos = page.evaluate("fetch('/api/v1/historico/presidente/br').then(r => r.json()).then(d => d.total_pontos)")
    page.get_by_role("button", name="Ver como tabela").click()
    assert page.locator(".grafico-tabela").is_visible() and page.locator(".grafico-area").is_hidden()
    assert page.locator(".grafico-tabela tbody tr").count() == pontos >= 6
    assert page.eval_on_selector_all(".grafico-tabela thead th", "els => els.map(e => e.textContent)")[:3] == ["Horário", "Seções totalizadas", "ALFA"]
    page.get_by_role("button", name="Ver como gráfico").click()
    assert page.locator(".grafico-area").is_visible() and page.locator(".grafico-tabela").is_hidden()


def test_grafico_nas_paginas_das_ufs_so_consulta_a_aba_visivel(abrir, grafico_pronto):
    page, _ = abrir("/uf/sp", pilha=grafico_pronto)
    esperar(page, "document.querySelectorAll('[role=tab]').length === 3")
    esperar(page, "document.querySelectorAll('#painel-presidente .grafico').length === 1")
    assert page.locator("#painel-governador .grafico").count() == 1 and page.locator("#painel-senador .grafico").count() == 1
    pedidos = []
    page.on("request", lambda r: pedidos.append(r.url) if "/api/v1/historico/" in r.url else None)
    page.get_by_role("tab", name="Senador").click()
    page.wait_for_timeout(2500)
    assert any("/historico/senador/sp" in u for u in pedidos)
    assert not any("/historico/governador/" in u for u in pedidos)  # abas ocultas não geram requisições


def test_grafico_no_celular_cabe_na_tela_e_responde_ao_toque(abrir, grafico_pronto):
    page, erros = abrir("/", largura=390, altura=844, toque=True, pilha=grafico_pronto)
    esperar(page, "document.querySelectorAll('.grafico svg path.serie').length === 3")
    page.locator(".grafico").scroll_into_view_if_needed()
    assert page.locator(".grafico .rotulo-fim").count() == 0  # tela estreita: a legenda carrega a identificação
    assert page.locator(".grafico .legenda-linhas li").count() == 3
    svg = page.locator(".grafico svg").bounding_box()
    assert svg["x"] >= 0 and svg["x"] + svg["width"] <= 390
    assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0
    caixa = page.locator(".grafico .captura").bounding_box()
    page.touchscreen.tap(caixa["x"] + caixa["width"] * 0.5, caixa["y"] + caixa["height"] * 0.5)
    assert page.locator("#dica").is_visible()  # a leitura continua depois de tirar o dedo
    assert page.locator("#dica .dica-linha").count() == 3
    page.touchscreen.tap(195, 20)  # toque fora do gráfico fecha a dica
    page.wait_for_timeout(200)
    assert page.locator("#dica").is_hidden()
    assert erros == []


def test_no_toque_a_dica_do_ranking_e_ignorada(abrir):
    page, _ = abrir("/", largura=390, altura=844, toque=True)
    esperar(page, "document.querySelectorAll('.cand').length === 6")
    page.locator(".cand").first.tap()
    page.wait_for_timeout(300)
    assert page.locator("#dica").is_hidden()  # no toque a informação já está na linha; nada de dica "grudada"


@pytest.mark.parametrize("esquema", ["light", "dark"])
def test_acessibilidade_da_pagina_com_grafico(navegador, grafico_pronto, esquema):
    axe_pw = pytest.importorskip("axe_playwright_python.sync_playwright")
    ctx = navegador.new_context(viewport={"width": 1280, "height": 900}, color_scheme=esquema, locale="pt-BR", bypass_csp=True)
    try:
        page = ctx.new_page()
        page.goto(f"{grafico_pronto.url}/?{INTERVALO}", wait_until="networkidle")
        esperar(page, "document.querySelectorAll('.grafico svg path.serie').length === 3")
        page.wait_for_timeout(1500)
        violacoes = axe_pw.Axe().run(page).response["violations"]
        resumo = [f"{v['id']} [{v['impact']}] {v['help']}: " + "; ".join(str(n['target']) for n in v["nodes"][:3]) for v in violacoes]
        assert not violacoes, "\n".join(resumo)
    finally:
        ctx.close()


# ---- responsividade: celular, tablet e telas grandes ---------------------------------------------------------------
TELAS = [(360, 740, True), (390, 844, True), (600, 960, True), (768, 1024, True), (820, 1180, True), (1024, 768, True), (1280, 900, False)]

ALVOS_DE_TOQUE = """() => {
  const seletores = ['.aba', '#btn-tema', '#sel-uf', '.seg button', '.btn-texto', '[role=tab]', '.th-botao', '.turnos a', '#busca-mun'];
  const pequenos = [];
  for (const s of seletores) for (const el of document.querySelectorAll(s)) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.height < 43.5 || r.width < 43.5) pequenos.push(`${s} ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return pequenos;
}"""


@pytest.mark.parametrize("largura, altura, toque", TELAS)
def test_responsivo_sem_rolagem_horizontal_e_com_alvos_de_toque_adequados(abrir, largura, altura, toque):
    codigo = Simulacao.codigo_municipio("sp", 0)
    for caminho in ("/", "/uf/sp", "/senadores", f"/municipio/sp/{codigo:05d}"):
        page, erros = abrir(caminho, largura=largura, altura=altura, toque=toque)
        esperar(page, "document.querySelectorAll('.cand, .tabela tbody tr').length > 3")
        page.wait_for_timeout(800)
        sobra = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert sobra <= 0, f"{caminho} em {largura}px tem {sobra}px de rolagem horizontal"
        if toque:
            assert page.evaluate("matchMedia('(pointer: coarse)').matches")
            assert page.evaluate(ALVOS_DE_TOQUE) == [], f"{caminho} em {largura}px: alvos de toque menores que 44 px"
        assert erros == [], f"{caminho} em {largura}px: {erros}"


def test_layout_celular_empilha_e_tablet_poe_lado_a_lado(abrir):
    esperar_tudo = "document.querySelectorAll('.cand').length === 6 && document.querySelectorAll('.bloco').length === 28"
    # celular: ranking em cima do mapa; o 5º indicador ocupa a linha inteira
    page, _ = abrir("/", largura=390, altura=844, toque=True)
    esperar(page, esperar_tudo)
    ranking, mapa = page.locator(".duas-colunas > .cartao").nth(0).bounding_box(), page.locator(".duas-colunas > .cartao").nth(1).bounding_box()
    assert mapa["y"] > ranking["y"] + ranking["height"] - 1 and abs(ranking["width"] - mapa["width"]) < 2
    kpis = [k.bounding_box() for k in page.locator(".kpi").all()]
    assert abs(kpis[0]["y"] - kpis[1]["y"]) < 2 and kpis[4]["width"] > kpis[0]["width"] * 1.8 and kpis[4]["y"] > kpis[2]["y"]
    # tablet em retrato: ranking e mapa lado a lado; os 5 indicadores numa linha só
    page, _ = abrir("/", largura=768, altura=1024, toque=True)
    esperar(page, esperar_tudo)
    ranking, mapa = page.locator(".duas-colunas > .cartao").nth(0).bounding_box(), page.locator(".duas-colunas > .cartao").nth(1).bounding_box()
    assert abs(ranking["y"] - mapa["y"]) < 2 and mapa["x"] > ranking["x"] + ranking["width"] - 1
    assert len({round(k.bounding_box()["y"]) for k in page.locator(".kpi").all()}) == 1


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
