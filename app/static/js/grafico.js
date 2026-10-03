// Gráfico de linhas: evolução do percentual dos primeiros colocados ao longo da apuração.
//
// Cada ponto é um momento em que o painel recebeu números novos do TSE. Mira vertical que acompanha o
// ponteiro (mouse, toque ou setas do teclado) com uma dica que lista todas as linhas naquele ponto, legenda
// sempre presente, rótulos diretos nas pontas só quando cabem sem colidir, e uma tabela equivalente.
import { h, limpar, svg } from "./dom.js";
import { Atualizador } from "./net.js";
import * as dica from "./dica.js";
import * as fmt from "./fmt.js";

const MIN_PONTOS = 2;
// passos possíveis do eixo de horário, em segundos (de 5 s, nos primeiros instantes, a 4 h)
const PASSOS_SEGUNDOS = [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 14400];
const DESLOCAMENTO_BRASILIA_S = 3 * 3600; // UTC-3 o ano todo (sem horário de verão desde 2019)

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

export class GraficoEvolucao {
  /** `url`: endpoint /api/v1/historico/...; `metaCinquenta`: marca a linha de 50% quando ela cabe no gráfico. */
  constructor({ url, titulo = "Evolução da apuração", metaCinquenta = false, intervaloMs = 15000 }) {
    this.metaCinquenta = metaCinquenta;
    this.modo = "hora"; // eixo horizontal: "hora" | "secoes"
    this.dados = null;
    this.larg = 0;
    this.indice = null;
    this.geo = null;
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
    this.nota = h("p", { class: "sub" });
    this.vazio = h("p", { class: "vazio", hidden: true });
    this.area = h("div", {
      class: "grafico-area", tabindex: "0", role: "group",
      "aria-label": "Gráfico de evolução. Use as setas para a esquerda e a direita para percorrer os momentos.",
    });
    this.tabelaBox = h("div", { class: "grafico-tabela", hidden: true });
    const botoesEixo = [["hora", "Horário"], ["secoes", "% das seções"]].map(([modo, rotulo]) =>
      h("button", {
        type: "button", "aria-pressed": String(modo === this.modo), dados: { modo }, texto: rotulo,
        onclick: () => this.definirModo(modo),
      }));
    this.botoesEixo = botoesEixo;
    this.botaoTabela = h("button", {
      type: "button", class: "btn-texto", "aria-pressed": "false", texto: "Ver como tabela",
      onclick: () => this.alternarTabela(),
    });
    this.el = h("section", { class: "cartao grafico" },
      h("div", { class: "grafico-cab" },
        h("div", {}, h("h2", { texto: titulo }), this.nota),
        h("div", { class: "grafico-ctl" },
          h("div", { class: "seg", role: "group", "aria-label": "Eixo horizontal" }, ...botoesEixo), this.botaoTabela)),
      this.legenda, this.vazio, this.area, this.tabelaBox);
    this.area.addEventListener("keydown", (ev) => this.aoTeclado(ev));
    this.area.addEventListener("blur", () => this.esconder());
    document.addEventListener("pointerdown", (ev) => {
      if (!this.area.contains(ev.target)) this.esconder(); // no toque, a mira fica até o próximo toque fora
    });
  }

  definirModo(modo) {
    this.modo = modo;
    for (const b of this.botoesEixo) b.setAttribute("aria-pressed", String(b.dataset.modo === modo));
    this.indice = null;
    this.render();
  }

  alternarTabela() {
    const mostrar = this.tabelaBox.hidden;
    this.tabelaBox.hidden = !mostrar;
    this.botaoTabela.setAttribute("aria-pressed", String(mostrar));
    this.botaoTabela.textContent = mostrar ? "Ver como gráfico" : "Ver como tabela";
    this.area.hidden = mostrar;
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
    if (!suficiente) {
      this.vazio.textContent = n === 0
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
        h("span", { class: "traco", "data-cor": String(s.cor) }), h("span", { class: "legenda-nome", texto: s.urna }),
        ultimo !== undefined ? h("span", { class: "sub", texto: fmt.pct2(ultimo) }) : null));
    }
  }

  desenhar(d) {
    const W = this.larg;
    const H = Math.round(Math.min(380, Math.max(230, W * (W < 520 ? 0.78 : 0.42))));
    const rotulosNoFim = W >= 760;
    const m = { t: 14, r: rotulosNoFim ? 150 : 16, b: 32, l: 44 };
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
      const t = svg("text", { class: "eixo-txt", x: m.l - 8, y: py(v) + 4, "text-anchor": "end" });
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
      eixo.push(svg("line", { class: "eixo-linha", x1: x, x2: x, y1: H - m.b, y2: H - m.b + 4 }));
      const t = svg("text", { class: "eixo-txt", x, y: H - m.b + 18, "text-anchor": "middle" });
      t.textContent = rotulo;
      eixo.push(t);
    }
    raiz.append(g("eixo-x", ...eixo));

    // linhas (cada série em segmentos contínuos; lacunas = candidato sem voto naquele ponto)
    const linhas = [];
    const pontaFinal = [];
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
      });
      linhas.push(svg("path", { class: "serie", "data-cor": String(s.cor), d: caminho }));
      if (ultimo) pontaFinal.push({ s, ...ultimo });
    }
    raiz.append(g("series", ...linhas));
    raiz.append(g("pontas", ...pontaFinal.map((p) => svg("circle", { class: "ponto-final", "data-cor": String(p.s.cor), cx: p.x, cy: p.y, r: 4.5 }))));

    // rótulos diretos nas pontas: só se couberem sem colidir (senão a legenda e a dica carregam a informação)
    if (rotulosNoFim && pontaFinal.length) {
      const ordenados = [...pontaFinal].sort((a, b) => a.y - b.y);
      const cabem = ordenados.every((p, i) => i === 0 || p.y - ordenados[i - 1].y >= 16);
      if (cabem) {
        raiz.append(g("rotulos-fim", ...ordenados.map((p) => {
          const t = svg("text", { class: "rotulo-fim", x: p.x + 10, y: p.y + 4 });
          t.textContent = `${p.s.urna} ${fmt.pct2(p.v)}`;
          return t;
        })));
      }
    }

    // mira + pontos que acompanham o ponteiro
    const mira = svg("line", { class: "mira", y1: m.t, y2: H - m.b, x1: 0, x2: 0, visibility: "hidden" });
    const pontosMira = d.series.map((s) => svg("circle", { class: "ponto-mira", "data-cor": String(s.cor), r: 4.5, cx: 0, cy: 0, visibility: "hidden" }));
    raiz.append(g("mira-grupo", mira, ...pontosMira));
    const captura = svg("rect", { class: "captura", x: m.l, y: m.t, width: larguraUtil, height: alturaUtil });
    raiz.append(captura);

    this.geo = { xs, m, W, H, py, mira, pontosMira, raiz };
    limpar(this.area).append(raiz);
    captura.addEventListener("pointermove", (ev) => this.aoPonteiro(ev));
    captura.addEventListener("pointerdown", (ev) => this.aoPonteiro(ev));
    captura.addEventListener("pointerleave", (ev) => {
      if (ev.pointerType !== "touch") this.esconder();
    });
    if (this.indice !== null && this.indice < xs.length) this.posicionarMira(this.indice);
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
