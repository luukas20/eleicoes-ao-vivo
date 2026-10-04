// Gráfico de linhas: evolução do percentual dos primeiros colocados ao longo da apuração.
//
// Cada ponto é um momento em que o painel recebeu números novos do TSE. Mira vertical que acompanha o
// ponteiro (mouse, toque ou setas do teclado) com uma dica que lista todas as linhas naquele ponto, legenda
// sempre presente, rótulos diretos nas pontas (etiquetas na cor do partido, afastadas para não se sobreporem)
// e uma tabela equivalente.
import { h, limpar, segmentado, svg } from "./dom.js";
import { Atualizador } from "./net.js";
import * as dica from "./dica.js";
import * as fmt from "./fmt.js";

const MIN_PONTOS = 2;
// passos possíveis do eixo de horário, em segundos (de 5 s, nos primeiros instantes, a 4 h)
const PASSOS_SEGUNDOS = [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 14400];
const DESLOCAMENTO_BRASILIA_S = 3 * 3600; // UTC-3 o ano todo (sem horário de verão desde 2019)
const MAX_AMOSTRAS = 40;   // até aqui, cada atualização do TSE aparece como um pontinho na linha
const ALTURA_ETIQUETA = 22;
const FOLGA_ETIQUETAS = 4; // espaço mínimo entre duas etiquetas de ponta

// Faixa do eixo Y em números redondos: as duas pontas do eixo sempre têm marcação.
function escalaY(valores) {
  let baixo = Math.max(0, Math.floor((Math.min(...valores) - 2) / 5) * 5);
  let alto = Math.min(100, Math.ceil((Math.max(...valores) + 2) / 5) * 5);
  if (alto - baixo < 10) {
    alto = Math.min(100, baixo + 10);
    baixo = Math.max(0, alto - 10);
  }
  const passo = alto - baixo <= 20 ? 5 : alto - baixo <= 50 ? 10 : 20;
  baixo = Math.floor(baixo / passo) * passo;
  alto = Math.min(100, Math.ceil(alto / passo) * passo);
  return { baixo, alto, passo };
}

/** Afasta posições verticais (ordenadas) para que fiquem a `passo` uma da outra, deslocando o grupo o mínimo possível. */
function afastar(ideais, passo, topo, base) {
  const pos = [...ideais];
  for (let i = 1; i < pos.length; i++) pos[i] = Math.max(pos[i], pos[i - 1] + passo);
  const deslocamento = pos.reduce((soma, p, i) => soma + (p - ideais[i]), 0) / (pos.length || 1);
  let subir = deslocamento;
  if (pos.length) subir = Math.min(subir, pos[0] - topo);          // não passa do topo do desenho
  if (pos.length) subir = Math.max(subir, pos.at(-1) - base);      // nem da base
  return pos.map((p) => p - subir);
}

/** Esqueleto do gráfico (antes de haver linhas para desenhar): a base e três linhas apagadas, pontilhadas. */
function esqueleto() {
  const raiz = svg("svg", { viewBox: "0 0 600 150", class: "esqueleto", "aria-hidden": "true", focusable: "false", preserveAspectRatio: "none" });
  raiz.append(svg("line", { class: "eixo-linha", x1: 0, x2: 600, y1: 142, y2: 142 }));
  for (const y of [38, 76, 112]) {
    raiz.append(svg("path", { class: "fantasma", d: `M0 ${y + 8} C 120 ${y + 8}, 200 ${y - 8}, 320 ${y}, 440 ${y + 8}, 520 ${y - 4}, 600 ${y - 2}` }));
  }
  return raiz;
}

export class GraficoEvolucao {
  /** `url`: endpoint /api/v1/historico/...; `metaCinquenta`: marca a linha de 50% quando ela cabe no gráfico. */
  constructor({ url, titulo = "Evolução da apuração", metaCinquenta = false, intervaloMs = 15000 }) {
    this.metaCinquenta = metaCinquenta;
    this.modo = "hora"; // eixo horizontal: "hora" | "secoes"
    this.dados = null;
    this.larg = 0;
    this.indice = null;
    this.geo = null;
    this.jaDesenhou = false; // a animação de entrada das linhas só acontece na primeira pintura
    this.montar(titulo);
    this.atualizador = new Atualizador({
      url,
      intervaloMs,
      aoDados: (d) => {
        this.dados = d;
        this.render();
      },
      aoIndisponivel: () => {},
      aoErro: () => {},
    });
    this.atualizador.pausado = true;
    this.ativo = false;
    this.iniciado = false;
    new ResizeObserver((entradas) => {
      const largura = Math.floor(entradas[0].contentRect.width);
      if (largura > 0 && Math.abs(largura - this.larg) > 1) {
        this.larg = largura;
        this.render();
      }
    }).observe(this.area);
  }

  /** Só consulta a API enquanto o gráfico está visível (ex.: aba selecionada). */
  definirAtivo(ativo) {
    if (ativo === this.ativo) return;
    this.ativo = ativo;
    this.atualizador.pausado = !ativo;
    if (!ativo) return;
    if (!this.iniciado) {
      this.iniciado = true;
      this.atualizador.iniciar();
    } else {
      this.atualizador.buscar();
    }
  }

  // ---- DOM fixo ---------------------------------------------------------------------------------------
  montar(titulo) {
    this.legenda = h("ul", { class: "legenda-linhas" });
    this.nota = h("p", { class: "grafico-nota" });
    this.mensagem = h("p", { class: "vazio-texto" });
    this.vazio = h("div", { class: "vazio vazio--grafico", hidden: true }, esqueleto(), this.mensagem);
    this.area = h("div", {
      class: "grafico-area", tabindex: "0", role: "group",
      "aria-label": "Gráfico de evolução. Use as setas para a esquerda e a direita para percorrer os momentos.",
    });
    this.tabelaBox = h("div", { class: "grafico-tabela", hidden: true });
    // os controles são os mesmos do mapa (Mapa | Blocos): um indicador que desliza até a opção ativa
    this.eixo = segmentado({
      rotulo: "Eixo horizontal", ativo: this.modo, aoEscolher: (modo) => this.definirModo(modo),
      opcoes: [{ valor: "hora", texto: "Horário" }, { valor: "secoes", texto: "% das seções" }],
    });
    this.visao = segmentado({
      rotulo: "Forma de exibir a evolução", ativo: "grafico", aoEscolher: (v) => this.definirVisao(v),
      opcoes: [{ valor: "grafico", texto: "Gráfico", icone: "linhas" }, { valor: "tabela", texto: "Tabela", icone: "tabela" }],
    });
    this.el = h("section", { class: "sec grafico" },
      h("header", { class: "sec-cab" },
        h("h2", { class: "sec-tit", texto: titulo }),
        h("div", { class: "grafico-ctl" }, this.eixo.el, this.visao.el)),
      h("div", { class: "cartao" }, this.legenda, this.vazio, this.area, this.tabelaBox, this.nota));
    this.area.addEventListener("keydown", (ev) => this.aoTeclado(ev));
    this.area.addEventListener("blur", () => this.esconder());
    document.addEventListener("pointerdown", (ev) => {
      if (!this.area.contains(ev.target)) this.esconder(); // no toque, a mira fica até o próximo toque fora
    });
  }

  definirModo(modo) {
    this.modo = modo;
    this.eixo.definir(modo);
    this.indice = null;
    this.render();
  }

  /** Gráfico ou tabela equivalente. */
  definirVisao(visao) {
    const tabela = visao === "tabela";
    this.visao.definir(visao);
    this.tabelaBox.hidden = !tabela;
    this.area.hidden = tabela;
    this.esconder();
    this.render();
  }

  // ---- desenho ----------------------------------------------------------------------------------------
  render() {
    const d = this.dados;
    if (!d) return;
    const n = d.pontos.length;
    this.pintarLegenda(d);
    const suficiente = n >= MIN_PONTOS;
    this.vazio.hidden = suficiente;
    this.eixo.el.hidden = this.visao.el.hidden = !suficiente;
    if (!suficiente) {
      this.mensagem.textContent = n === 0
        ? "O gráfico aparece quando as primeiras urnas forem totalizadas e o TSE liberar os votos."
        : "Já há um registro. As linhas aparecem a partir da segunda atualização do TSE.";
      this.area.hidden = true;
      this.tabelaBox.hidden = true;
      this.nota.textContent = "";
      return;
    }
    this.nota.textContent = `Cada ponto é um momento em que o painel recebeu números novos do TSE, desde ${fmt.hora(d.desde)} (horário de Brasília). `
      + "Se o painel foi iniciado depois do começo da apuração, o início da curva não aparece.";
    if (!this.tabelaBox.hidden) {
      this.pintarTabela(d);
      return;
    }
    this.area.hidden = false;
    if (this.larg > 0) this.desenhar(d);
  }

  pintarLegenda(d) {
    limpar(this.legenda);
    for (const s of d.series) {
      const ultimo = [...s.pct].reverse().find((v) => v !== null && v !== undefined);
      this.legenda.append(h("li", {},
        h("span", { class: "traco", "data-cor": s.cor }), h("span", { class: "legenda-nome", texto: s.urna }),
        s.partido ? h("span", { class: "sigla", "data-cor": s.cor, texto: s.partido }) : null,
        ultimo !== undefined ? h("span", { class: "legenda-pct", texto: fmt.pct2(ultimo) }) : null));
    }
  }

  desenhar(d) {
    const W = this.larg;
    const H = Math.round(Math.min(400, Math.max(240, W * (W < 520 ? 0.8 : 0.42))));
    const rotulosNoFim = W >= 760;
    const m = { t: 18, r: rotulosNoFim ? 196 : 18, b: 34, l: 46 };
    const larguraUtil = W - m.l - m.r;
    const alturaUtil = H - m.t - m.b;

    // eixo X
    const valoresX = d.pontos.map((p) => (this.modo === "hora" ? Date.parse(p.t) : p.pst));
    let [x0, x1] = this.modo === "hora" ? [Math.min(...valoresX), Math.max(...valoresX)] : [0, 100];
    if (x1 - x0 < 1) [x0, x1] = [x0 - 30000, x1 + 30000];
    const px = (v) => m.l + ((v - x0) / (x1 - x0)) * larguraUtil;
    const xs = valoresX.map(px);

    // eixo Y
    const todos = d.series.flatMap((s) => s.pct.filter((v) => v !== null && v !== undefined));
    const { baixo: yMin, alto: yMax, passo: passoY } = escalaY(todos);
    const py = (v) => m.t + ((yMax - v) / (yMax - yMin)) * alturaUtil;

    const raiz = svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": this.resumo(d) });
    const g = (classe, ...filhos) => svg("g", { class: classe }, ...filhos);

    const grade = [];
    for (let v = Math.ceil(yMin / passoY) * passoY; v <= yMax; v += passoY) {
      grade.push(svg("line", { class: "grade-linha", x1: m.l, x2: W - m.r, y1: py(v), y2: py(v) }));
      const t = svg("text", { class: "eixo-txt", x: m.l - 10, y: py(v) + 4, "text-anchor": "end" });
      t.textContent = `${v}%`;
      grade.push(t);
    }
    if (this.metaCinquenta && yMin < 50 && yMax > 50) {
      grade.push(svg("line", { class: "meta-50", x1: m.l, x2: W - m.r, y1: py(50), y2: py(50) }));
    }
    raiz.append(g("grade", ...grade));

    const eixo = [svg("line", { class: "eixo-linha", x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b })];
    for (const { valor, rotulo } of this.marcasX(x0, x1, W)) {
      const x = px(valor);
      eixo.push(svg("line", { class: "eixo-linha", x1: x, x2: x, y1: H - m.b, y2: H - m.b + 5 }));
      const t = svg("text", { class: "eixo-txt", x, y: H - m.b + 20, "text-anchor": "middle" });
      t.textContent = rotulo;
      eixo.push(t);
    }
    raiz.append(g("eixo-x", ...eixo));

    // linhas (cada série em segmentos contínuos; lacunas = candidato sem voto naquele ponto)
    const linhas = [];
    const amostras = [];
    const pontaFinal = [];
    const comPontinhos = xs.length <= MAX_AMOSTRAS && W >= 480;
    for (const s of d.series) {
      let caminho = "";
      let aberto = false;
      let ultimo = null;
      s.pct.forEach((v, i) => {
        if (v === null || v === undefined) {
          aberto = false;
          return;
        }
        caminho += `${aberto ? "L" : "M"}${xs[i].toFixed(1)} ${py(v).toFixed(1)}`;
        aberto = true;
        ultimo = { x: xs[i], y: py(v), v };
        if (comPontinhos) amostras.push(svg("circle", { class: "amostra", "data-cor": s.cor, cx: xs[i].toFixed(1), cy: py(v).toFixed(1), r: 3 }));
      });
      linhas.push(svg("path", { class: "serie", "data-cor": s.cor, d: caminho }));
      if (ultimo) pontaFinal.push({ s, ...ultimo });
    }
    raiz.append(g("series", ...linhas));
    if (amostras.length) raiz.append(g("amostras", ...amostras));
    raiz.append(g("pontas", ...pontaFinal.map((p) => svg("circle", { class: "ponto-final", "data-cor": p.s.cor, cx: p.x, cy: p.y, r: 5 }))));

    // mira + pontos que acompanham o ponteiro
    const mira = svg("line", { class: "mira", y1: m.t, y2: H - m.b, x1: 0, x2: 0, visibility: "hidden" });
    const pontosMira = d.series.map((s) => svg("circle", { class: "ponto-mira", "data-cor": s.cor, r: 5, cx: 0, cy: 0, visibility: "hidden" }));
    raiz.append(g("mira-grupo", mira, ...pontosMira));
    const captura = svg("rect", { class: "captura", x: m.l, y: m.t, width: larguraUtil, height: alturaUtil });
    raiz.append(captura);

    this.geo = { xs, m, W, H, py, mira, pontosMira, raiz };
    limpar(this.area).append(raiz);
    this.animarEntrada(linhas);
    if (rotulosNoFim && pontaFinal.length) this.etiquetasDePonta(raiz, captura, pontaFinal, m, H);
    captura.addEventListener("pointermove", (ev) => this.aoPonteiro(ev));
    captura.addEventListener("pointerdown", (ev) => this.aoPonteiro(ev));
    captura.addEventListener("pointerleave", (ev) => {
      if (ev.pointerType !== "touch") this.esconder();
    });
    if (this.indice !== null && this.indice < xs.length) this.posicionarMira(this.indice);
  }

  /** As linhas se desenham da esquerda para a direita na primeira vez (depois, a cada novo dado, só se atualizam). */
  animarEntrada(linhas) {
    if (this.jaDesenhou) return;
    this.jaDesenhou = true;
    for (const linha of linhas) {
      const comprimento = linha.getTotalLength ? Math.ceil(linha.getTotalLength()) : 0;
      if (!comprimento) continue;
      linha.style.setProperty("--comprimento", String(comprimento));
      linha.classList.add("entra");
    }
  }

  /** Etiqueta na ponta de cada linha: nome e valor sobre a cor do partido; se duas ficam juntas, uma é afastada e ligada por um traço. */
  etiquetasDePonta(raiz, antesDe, pontas, m, H) {
    const ordenadas = [...pontas].sort((a, b) => a.y - b.y);
    const passo = ALTURA_ETIQUETA + FOLGA_ETIQUETAS;
    const alturas = afastar(ordenadas.map((p) => p.y), passo, m.t + ALTURA_ETIQUETA / 2, H - m.b - ALTURA_ETIQUETA / 2);
    const grupo = svg("g", { class: "rotulos-fim", "aria-hidden": "true" });
    ordenadas.forEach((p, i) => {
      const texto = svg("text", { x: p.x + 24, y: alturas[i], "dominant-baseline": "central" });
      texto.textContent = `${p.s.urna} ${fmt.pct2(p.v)}`;
      const rotulo = svg("g", { class: "rotulo-fim", "data-cor": p.s.cor });
      const fundo = svg("rect", { x: p.x + 14, y: alturas[i] - ALTURA_ETIQUETA / 2, height: ALTURA_ETIQUETA, rx: 6 });
      const ligacao = svg("path", { class: "rotulo-fim-ligacao", d: `M${p.x + 5} ${p.y} L${p.x + 14} ${alturas[i]}` });
      rotulo.append(ligacao, fundo, texto);
      grupo.append(rotulo);
    });
    raiz.insertBefore(grupo, antesDe.parentNode.querySelector(".mira-grupo"));
    // a largura do texto só é conhecida depois de ele estar na página; nomes muito longos são encurtados para caber na margem
    const maxLargura = m.r - 14 - 6;
    [...grupo.children].forEach((rotulo, i) => {
      const texto = rotulo.querySelector("text");
      const valor = fmt.pct2(ordenadas[i].v);
      let nome = ordenadas[i].s.urna;
      let largura = texto.getComputedTextLength();
      while (largura + 20 > maxLargura && nome.length > 4) {
        nome = nome.slice(0, -1);
        texto.textContent = `${nome.trimEnd()}… ${valor}`;
        largura = texto.getComputedTextLength();
      }
      rotulo.querySelector("rect").setAttribute("width", String(Math.ceil(largura + 20)));
    });
  }

  marcasX(x0, x1, W) {
    if (this.modo === "secoes") {
      const passo = W < 520 ? 25 : 20;
      return Array.from({ length: Math.floor(100 / passo) + 1 }, (_, i) => ({ valor: i * passo, rotulo: `${i * passo}%` }));
    }
    const segundos = (x1 - x0) / 1000;
    const maximo = W < 480 ? 3 : W < 760 ? 5 : 8;
    const passo = PASSOS_SEGUNDOS.find((p) => segundos / p <= maximo) || PASSOS_SEGUNDOS.at(-1);
    const rotular = passo < 60 ? fmt.hora : fmt.horaMinuto; // passos curtos mostram os segundos
    const primeiro = Math.ceil((x0 / 1000 - DESLOCAMENTO_BRASILIA_S) / passo) * passo + DESLOCAMENTO_BRASILIA_S;
    const marcas = [];
    for (let s = primeiro; s * 1000 <= x1; s += passo) marcas.push({ valor: s * 1000, rotulo: rotular(s * 1000) });
    if (marcas.length === 0) { // intervalo curtíssimo: ao menos o começo e o fim
      marcas.push({ valor: x0, rotulo: fmt.hora(x0) }, { valor: x1, rotulo: fmt.hora(x1) });
    }
    return marcas;
  }

  resumo(d) {
    const partes = d.series.map((s) => {
      const ultimo = [...s.pct].reverse().find((v) => v !== null && v !== undefined);
      return `${s.urna} ${ultimo !== undefined ? fmt.pct2(ultimo) : "sem votos"}`;
    });
    return `Evolução do percentual dos votos desde ${fmt.hora(d.desde)}. Situação mais recente: ${partes.join("; ")}.`;
  }

  // ---- interação --------------------------------------------------------------------------------------
  maisProximo(x) {
    const xs = this.geo.xs;
    let lo = 0;
    let hi = xs.length - 1;
    while (hi - lo > 1) {
      const meio = (lo + hi) >> 1;
      if (xs[meio] < x) lo = meio;
      else hi = meio;
    }
    return Math.abs(xs[lo] - x) <= Math.abs(xs[hi] - x) ? lo : hi;
  }

  posicionarMira(i) {
    const { xs, mira, pontosMira, py } = this.geo;
    this.indice = i;
    mira.setAttribute("x1", xs[i]);
    mira.setAttribute("x2", xs[i]);
    mira.setAttribute("visibility", "visible");
    this.dados.series.forEach((s, k) => {
      const v = s.pct[i];
      const ponto = pontosMira[k];
      if (v === null || v === undefined) {
        ponto.setAttribute("visibility", "hidden");
        return;
      }
      ponto.setAttribute("cx", xs[i]);
      ponto.setAttribute("cy", py(v));
      ponto.setAttribute("visibility", "visible");
    });
  }

  conteudoDica(i) {
    const d = this.dados;
    const p = d.pontos[i];
    const corpo = h("div", {}, dica.titulo(`${fmt.hora(p.t)} · ${fmt.pct2(p.pst)} das seções`));
    for (const s of d.series) {
      const v = s.pct[i];
      if (v === null || v === undefined) continue;
      corpo.append(dica.linha(s.cor, fmt.pct2(v), s.urna, s.votos[i] != null ? `${fmt.inteiro(s.votos[i])} votos` : ""));
    }
    return corpo;
  }

  aoPonteiro(ev) {
    if (!this.geo) return;
    const caixa = this.geo.raiz.getBoundingClientRect();
    const i = this.maisProximo(ev.clientX - caixa.left);
    this.posicionarMira(i);
    // no toque o dedo cobriria a dica: ela fica no topo do gráfico
    const y = ev.pointerType === "touch" ? caixa.top + 8 : ev.clientY;
    dica.mostrar(this.conteudoDica(i), ev.clientX, y);
  }

  aoTeclado(ev) {
    if (!this.geo || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(ev.key)) return;
    ev.preventDefault();
    const ultimo = this.geo.xs.length - 1;
    let i = this.indice === null ? ultimo : this.indice;
    if (ev.key === "ArrowLeft") i = Math.max(0, i - 1);
    else if (ev.key === "ArrowRight") i = Math.min(ultimo, i + 1);
    else if (ev.key === "Home") i = 0;
    else i = ultimo;
    this.posicionarMira(i);
    const caixa = this.geo.raiz.getBoundingClientRect();
    dica.mostrar(this.conteudoDica(i), caixa.left + this.geo.xs[i], caixa.top + this.geo.m.t + 8);
  }

  esconder() {
    dica.ocultar();
    if (!this.geo) return;
    this.geo.mira.setAttribute("visibility", "hidden");
    this.geo.pontosMira.forEach((p) => p.setAttribute("visibility", "hidden"));
    this.indice = null;
  }

  // ---- tabela equivalente -----------------------------------------------------------------------------
  pintarTabela(d) {
    const cabecalho = h("tr", {}, h("th", { scope: "col", texto: "Horário" }), h("th", { scope: "col", class: "num", texto: "Seções totalizadas" }),
      ...d.series.map((s) => h("th", { scope: "col", class: "num", texto: s.urna })));
    const linhas = d.pontos.map((p, i) => h("tr", {},
      h("td", { texto: fmt.hora(p.t) }), h("td", { class: "num", texto: fmt.pct2(p.pst) }),
      ...d.series.map((s) => h("td", { class: "num", texto: s.pct[i] === null || s.pct[i] === undefined ? "—" : fmt.pct2(s.pct[i]) }))));
    limpar(this.tabelaBox).append(
      h("table", { class: "tabela" }, h("caption", { class: "so-leitor", texto: "Percentual dos primeiros colocados a cada atualização" }),
        h("thead", {}, cabecalho), h("tbody", {}, ...linhas.reverse())), // mais recente primeiro
    );
  }
}
