// Mapa geográfico das UFs: cada estado é um polígono pintado com a cor de quem lidera.
//
// O desenho vem pronto de /static/data/mapa-ufs.json (gerado por tools/gerar_mapa.py a partir da malha do IBGE).
// Os polígonos ficam numa camada escalada por uma transformação; rótulos e chamadas ficam em pixels da tela, para o
// texto ter sempre o mesmo tamanho (nítido num celular ou num telão) e para que um rótulo só apareça dentro do
// estado quando realmente cabe. Estados pequenos demais ganham uma "chamada": etiqueta ao lado, com uma linha até o estado.
import { h, svg } from "./dom.js";
import * as dica from "./dica.js";
import { Mapa, descreverUf, dicaDeUf, liderDaUf } from "./componentes.js";

const URL_GEO = "/static/data/mapa-ufs.json";
const COLUNA_LESTE = ["rn", "pb", "pe", "al", "se"]; // chamadas empilhadas numa coluna só, no mar a leste do Nordeste
const INTERIOR = ["df"];       // sem costa por perto: a etiqueta procura um canto livre sobre os estados vizinhos
// onde tentar a etiqueta de uma UF no interior: deslocamento (px, para uma etiqueta de 26 px de altura) do centro dela
const CANDIDATAS_INTERIOR = [[30, 0], [-30, -20], [30, -26], [-30, 22], [0, -34], [0, 34], [-44, 0], [46, 12]];
const FOLGA_CHAMADA = 14;      // px entre a costa e a etiqueta
const MARGEM_CHAMADAS = 46;    // px reservados à direita do desenho para essa coluna
const FOLGA_ROTULO = 3;        // px de ar, no total, entre o texto e as bordas do estado para o rótulo ser desenhado dentro dele
const CHAVE_VISAO = "mapa-visao";

const lerVisao = () => {
  try {
    return localStorage.getItem(CHAVE_VISAO) === "blocos" ? "blocos" : "mapa";
  } catch {
    return "mapa"; // armazenamento indisponível (janela privada etc.)
  }
};
const gravarVisao = (visao) => {
  try {
    localStorage.setItem(CHAVE_VISAO, visao);
  } catch {
    /* sem armazenamento: a escolha vale só nesta visita */
  }
};

const bate = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

export class MapaGeo {
  constructor() {
    this.dados = new Map();   // uf -> linha da API
    this.itens = [];          // um por UF: { geo, a, forma, rotulo, chamada }
    this.geo = null;
    this.hover = null;
    this.foco = null;
    this.medidas = null;      // { tam, larguras: Map(uf -> px) } — largura do texto de cada rótulo no tamanho atual
    this.layout = "";         // chave do último layout feito (evita refazer sem necessidade)
    this.caixa = h("div", { class: "mapa-geo" });
    this.pronto = this.carregar();
  }

  async carregar() {
    try {
      const resp = await fetch(URL_GEO);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.geo = await resp.json();
    } catch {
      return false;
    }
    this.construir();
    this.aplicar();
    new ResizeObserver(() => this.ajustar()).observe(this.caixa);
    this.ajustar();
    return true;
  }

  // ---- DOM (uma vez só) ---------------------------------------------------------------------------------
  construir() {
    const geo = this.geo;
    this.destaque = svg("path", { class: "uf-destaque" });
    this.camadaFormas = svg("g", { class: "formas" });
    this.camadaLinhas = svg("g", { class: "chamadas" });
    this.camadaRotulos = svg("g", { class: "rotulos" });
    this.camadaChips = svg("g", { class: "chips" });

    for (const u of geo.ufs) {
      const forma = svg("path", { class: "uf-forma", d: u.d });
      const a = svg("a", { class: "uf", href: `/uf/${u.uf}${window.location.search}`, "data-uf": u.uf, "aria-label": u.nome }, forma);
      const rotulo = svg("text", { class: "uf-rotulo", "aria-hidden": "true" });
      rotulo.textContent = u.uf.toUpperCase();
      const item = { geo: u, a, forma, rotulo, chamada: null };
      if (u.chamada) item.chamada = this.criarChamada(u);
      this.itens.push(item);
      this.camadaFormas.append(a);
      this.camadaRotulos.append(rotulo);
      this.ligar(a, u.uf);
    }
    this.camadaFormas.append(this.destaque);

    this.exterior = this.criarExterior();
    this.svg = svg(
      "svg",
      { class: "mapa-geo-svg", role: "group", "aria-label": "Mapa do Brasil por UF, pintado com a cor do candidato que lidera. Cada UF abre a página dela." },
      this.camadaFormas, this.camadaLinhas, this.camadaRotulos, this.camadaChips, this.exterior.el,
    );
    this.caixa.append(this.svg);
  }

  /** Etiqueta de uma UF pequena: linha + ponto no estado e um "chip" clicável (decorativo para leitores de tela). */
  criarChamada(u) {
    const retangulo = svg("rect", { rx: 4 });
    const texto = svg("text");
    texto.textContent = u.uf.toUpperCase();
    const chip = svg(
      "a",
      { class: "chip-uf", href: `/uf/${u.uf}${window.location.search}`, tabindex: "-1", "aria-hidden": "true" },
      retangulo, texto,
    );
    const linha = svg("line", { class: "chamada-linha" });
    const ponto = svg("circle", { class: "chamada-ponto", r: 2 });
    this.camadaLinhas.append(linha, ponto);
    this.camadaChips.append(chip);
    this.ligar(chip, u.uf);
    return { chip, retangulo, texto, linha, ponto };
  }

  /** Votos no exterior não têm lugar no mapa: um chip no canto, sem link (não existe página para ele). */
  criarExterior() {
    const retangulo = svg("rect", { rx: 4 });
    const texto = svg("text");
    texto.textContent = "Exterior";
    const el = svg("g", { class: "chip-uf chip-exterior", tabindex: "0", role: "img", "aria-label": "Exterior" }, retangulo, texto);
    dica.vincular(el, () => dicaDeUf(this.dados.get("zz")));
    return { el, retangulo, texto };
  }

  /** Dica e realce da UF: mouse, caneta e teclado (no toque o clique no link abre a página). */
  ligar(el, uf) {
    dica.vincular(el, () => dicaDeUf(this.dados.get(uf)));
    el.addEventListener("pointerenter", (ev) => {
      if (ev.pointerType !== "touch") this.realcar({ hover: uf });
    });
    el.addEventListener("pointerleave", () => this.realcar({ hover: null }));
    el.addEventListener("focus", () => this.realcar({ foco: uf }));
    el.addEventListener("blur", () => this.realcar({ foco: null }));
  }

  realcar({ hover = this.hover, foco = this.foco }) {
    this.hover = hover;
    this.foco = foco;
    const uf = hover || foco;
    const item = uf && this.itens.find((i) => i.geo.uf === uf);
    if (item) this.destaque.setAttribute("d", item.geo.d);
    else this.destaque.removeAttribute("d");
  }

  // ---- dados --------------------------------------------------------------------------------------------
  atualizar(ufs) {
    for (const l of ufs) this.dados.set(l.codigo, l);
    if (this.geo) this.aplicar();
  }

  aplicar() {
    const pintar = (el, lider) => (lider ? el.setAttribute("data-cor", String(lider.cor)) : el.removeAttribute("data-cor"));
    for (const item of this.itens) {
      const l = this.dados.get(item.geo.uf);
      const lider = liderDaUf(l);
      pintar(item.a, lider);
      pintar(item.rotulo, lider);
      if (item.chamada) pintar(item.chamada.chip, lider);
      item.a.setAttribute("aria-label", l ? descreverUf(item.geo.nome, l) : item.geo.nome);
    }
    const ex = this.dados.get("zz");
    pintar(this.exterior.el, liderDaUf(ex));
    this.exterior.el.setAttribute("aria-label", ex ? descreverUf("Exterior", ex) : "Exterior");
  }

  // ---- layout (a cada mudança de largura) ------------------------------------------------------------------
  ajustar() {
    const geo = this.geo;
    const larg = Math.floor(this.caixa.clientWidth);
    if (!geo || larg < 200) return; // oculto (visão de blocos) ou ainda sem tamanho
    const grosso = window.matchMedia("(pointer: coarse)").matches;
    const tam = larg < 360 ? 10 : larg < 520 ? 11 : 12;
    const chave = `${larg}/${tam}/${grosso}`;
    if (chave === this.layout) return;
    this.layout = chave;

    const k = (larg - MARGEM_CHAMADAS) / geo.largura;
    const alt = Math.round(geo.altura * k);
    this.svg.setAttribute("viewBox", `0 0 ${larg} ${alt}`);
    this.svg.dataset.tam = String(tam);
    this.camadaFormas.setAttribute("transform", `scale(${k})`);

    const medidas = this.medirTextos(tam);
    const alturaChip = grosso ? 26 : 20; // no toque, o mínimo confortável sem as etiquetas se atropelarem
    const folgaChip = 12;                // soma dos espaços laterais dentro da etiqueta

    // 1. quem tem a sigla dentro do estado e quem precisa de etiqueta ao lado
    const emChamada = [];
    for (const item of this.itens) {
      item.cabe = item.geo.lw * k >= medidas.get(item.geo.uf) + FOLGA_ROTULO;
      if (!item.cabe && item.chamada) emChamada.push(item);
    }
    for (const item of emChamada) item.largura = medidas.get(item.geo.uf) + folgaChip;

    // 2. etiquetas do litoral: a coluna do Nordeste fica alinhada e empilhada; as demais ficam ao lado da própria costa
    const costeiras = emChamada.filter((i) => !INTERIOR.includes(i.geo.uf));
    const coluna = costeiras.filter((i) => COLUNA_LESTE.includes(i.geo.uf)).sort((a, b) => a.geo.y - b.geo.y);
    const xColuna = coluna.length ? Math.max(...coluna.map((i) => i.geo.e * k)) + FOLGA_CHAMADA : 0;
    const alturas = this.empilhar(coluna.map((i) => i.geo.y * k), alturaChip + 2, alturaChip / 2);
    for (const item of costeiras) {
      const naColuna = coluna.indexOf(item);
      item.cx = Math.min(naColuna >= 0 ? xColuna : item.geo.e * k + FOLGA_CHAMADA, larg - item.largura - 1);
      item.cy = naColuna >= 0 ? alturas[naColuna] : item.geo.y * k;
    }
    this.separar(costeiras, alturaChip + 2); // ES e RJ, por exemplo, ficam perto demais em telas pequenas

    const retangulo = (x, cy, largura) => ({ x0: x, x1: x + largura, y0: cy - alturaChip / 2, y1: cy + alturaChip / 2 });
    const largEx = medidas.get("ex") + folgaChip;
    const ocupados = costeiras.map((i) => retangulo(i.cx, i.cy, i.largura));
    ocupados.push(retangulo(2, alt - alturaChip / 2 - 2, largEx));
    const siglas = new Map();
    for (const item of this.itens) {
      if (!item.cabe) continue;
      const meia = medidas.get(item.geo.uf) / 2 + 2; // com um respiro, para a etiqueta nunca encostar na sigla
      siglas.set(item, { x0: item.geo.x * k - meia, x1: item.geo.x * k + meia, y0: item.geo.y * k - tam * 0.7, y1: item.geo.y * k + tam * 0.7 });
    }
    ocupados.push(...siglas.values());

    // 3. etiquetas do interior (o DF): a primeira posição livre entre as candidatas, longe de siglas e de outras etiquetas
    for (const item of emChamada.filter((i) => INTERIOR.includes(i.geo.uf))) {
      const escala = alturaChip / 26;
      const ax = item.geo.x * k;
      const ay = item.geo.y * k;
      const tentativas = CANDIDATAS_INTERIOR.map(([dx, dy]) => ({
        cx: Math.max(1, Math.min(ax + dx * escala - item.largura / 2, larg - item.largura - 1)), cy: ay + dy * escala,
      }));
      const livre = tentativas.find((t) => !ocupados.some((o) => bate(o, retangulo(t.cx, t.cy, item.largura))));
      const escolhida = livre || tentativas[0];
      item.cx = escolhida.cx;
      item.cy = escolhida.cy;
      const caixa = retangulo(item.cx, item.cy, item.largura);
      ocupados.push(caixa);
      if (!livre) { // telas muito estreitas: a etiqueta, que é clicável, tem prioridade sobre a sigla de um estado grande
        for (const [outro, sigla] of siglas) if (!outro.chamada && bate(caixa, sigla)) outro.cabe = false;
      }
    }

    // 4. escreve no DOM
    for (const item of this.itens) {
      const u = item.geo;
      item.rotulo.toggleAttribute("data-oculto", !item.cabe);
      if (item.cabe) {
        item.rotulo.setAttribute("x", (u.x * k).toFixed(1));
        item.rotulo.setAttribute("y", (u.y * k).toFixed(1));
      }
      const c = item.chamada;
      if (!c) continue;
      const mostrar = emChamada.includes(item);
      for (const el of [c.chip, c.linha, c.ponto]) el.toggleAttribute("data-oculto", !mostrar);
      if (!mostrar) continue;
      this.posicionarChip(c, item.cx, item.cy, item.largura, alturaChip);
      c.linha.setAttribute("x1", (u.x * k).toFixed(1));
      c.linha.setAttribute("y1", (u.y * k).toFixed(1));
      c.linha.setAttribute("x2", (item.cx + item.largura / 2).toFixed(1)); // termina sob a etiqueta, que é desenhada por cima
      c.linha.setAttribute("y2", item.cy.toFixed(1));
      c.ponto.setAttribute("cx", (u.x * k).toFixed(1));
      c.ponto.setAttribute("cy", (u.y * k).toFixed(1));
    }
    this.posicionarChip(this.exterior, 2, alt - alturaChip / 2 - 2, largEx, alturaChip);
  }

  /** Empurra para baixo as etiquetas que se sobrepõem (só vale entre as que ocupam a mesma faixa horizontal). */
  separar(itens, passo) {
    const ordem = [...itens].sort((a, b) => a.cy - b.cy);
    ordem.forEach((item, i) => {
      for (const antes of ordem.slice(0, i)) {
        const mesmaFaixa = item.cx < antes.cx + antes.largura && antes.cx < item.cx + item.largura;
        if (mesmaFaixa && item.cy - antes.cy < passo) item.cy = antes.cy + passo;
      }
    });
  }

  /**
   * Afasta posições verticais (ordenadas) para que fiquem a pelo menos `passo` uma da outra, deslocando o grupo
   * inteiro o mínimo possível — as linhas das chamadas ficam curtas e para os dois lados, não só para baixo.
   */
  empilhar(ideais, passo, minimo) {
    const pos = [...ideais];
    for (let i = 1; i < pos.length; i++) pos[i] = Math.max(pos[i], pos[i - 1] + passo);
    const deslocamento = pos.reduce((soma, p, i) => soma + (p - ideais[i]), 0) / (pos.length || 1);
    const subir = Math.min(deslocamento, pos.length ? pos[0] - minimo : 0); // não passa do topo do desenho
    return pos.map((p) => p - subir);
  }

  posicionarChip(chip, x, cy, largura, altura) {
    chip.retangulo.setAttribute("x", x.toFixed(1));
    chip.retangulo.setAttribute("y", (cy - altura / 2).toFixed(1));
    chip.retangulo.setAttribute("width", largura.toFixed(1));
    chip.retangulo.setAttribute("height", String(altura));
    chip.texto.setAttribute("x", (x + largura / 2).toFixed(1));
    chip.texto.setAttribute("y", cy.toFixed(1));
  }

  /** Largura em pixels do texto de cada rótulo no tamanho de fonte atual (medida no navegador, que conhece a fonte). */
  medirTextos(tam) {
    if (this.medidas && this.medidas.tam === tam) return this.medidas.larguras;
    const larguras = new Map();
    for (const item of this.itens) {
      item.rotulo.removeAttribute("data-oculto"); // oculto, o texto não tem largura
      larguras.set(item.geo.uf, item.rotulo.getComputedTextLength());
    }
    larguras.set("ex", this.exterior.texto.getComputedTextLength());
    this.medidas = { tam, larguras };
    return larguras;
  }
}

/**
 * Mapa das UFs com duas visões: o mapa geográfico (padrão) e os blocos (grade de quadrados, com a barra de
 * progresso de cada UF). A escolha fica salva no navegador. Se o desenho do mapa não carregar, mostra os blocos.
 */
export class MapaUfs {
  constructor() {
    this.geo = new MapaGeo();
    this.blocos = new Mapa();
    this.ajuda = {
      mapa: h("p", { class: "sub", texto: "Cada estado leva a cor de quem lidera nele; só os três primeiros colocados ganham cor. Passe o mouse (ou use Tab) para ver os números; clique ou toque para abrir a UF. Os estados pequenos têm a sigla numa etiqueta ao lado." }),
      blocos: h("p", { class: "sub", texto: "Cada bloco é uma UF (EX = exterior). A cor indica o candidato à frente; a barrinha no pé do bloco mostra o quanto da UF já foi totalizado. Só os três primeiros colocados ganham cor." }),
    };
    this.botoes = ["mapa", "blocos"].map((visao) =>
      h("button", { type: "button", dados: { visao }, texto: visao === "mapa" ? "Mapa" : "Blocos", onclick: () => this.definir(visao, true) }));
    this.seletor = h("div", { class: "seg", role: "group", "aria-label": "Forma de exibir as UFs" }, ...this.botoes);
    this.el = h("div", { class: "mapa-ufs" }, this.seletor, this.ajuda.mapa, this.ajuda.blocos, this.geo.caixa, this.blocos.el);
    this.definir(lerVisao(), false);
    this.geo.pronto.then((ok) => {
      if (ok) return;
      this.seletor.hidden = true; // sem o desenho não há o que escolher
      this.definir("blocos", false);
    });
  }

  definir(visao, salvar) {
    this.visao = visao;
    for (const b of this.botoes) b.setAttribute("aria-pressed", String(b.dataset.visao === visao));
    this.geo.caixa.hidden = visao !== "mapa";
    this.ajuda.mapa.hidden = visao !== "mapa";
    this.blocos.el.hidden = visao !== "blocos";
    this.ajuda.blocos.hidden = visao !== "blocos";
    if (salvar) gravarVisao(visao);
  }

  atualizar(ufs) {
    this.geo.atualizar(ufs);
    this.blocos.atualizar(ufs);
  }
}
