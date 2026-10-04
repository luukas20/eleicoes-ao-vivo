// Hemiciclo: as vagas de um cargo proporcional desenhadas como assentos num semicírculo, agrupados por partido ou federação.
//
// Os assentos ficam em fileiras concêntricas, com mais assentos nas fileiras de fora, e são entregues às bancadas por
// ângulo (da esquerda para a direita): cada bancada ocupa uma fatia contínua do arco, como num plenário. As vagas que
// ainda não têm dono (a apuração está no começo) ficam vazias, à direita.
import { h, svg } from "./dom.js";
import * as dica from "./dica.js";

const RAIO = 100;          // unidades do desenho: o SVG escala com a largura da caixa
const FURO = 0.4;          // raio da fileira de dentro, em relação à de fora: abre o vão onde fica o número
const FOLGA = 0.8;         // diâmetro do assento em relação ao menor espaço entre dois assentos vizinhos
const RAIO_MAXIMO = 9;     // com poucas vagas os assentos não viram bolas gigantes
const ATRASO_MS = 2.2;     // entrada: um assento depois do outro (só na primeira pintura de cada tamanho)...
const ENTRADA_MAXIMA_MS = 1100; // ...mas o desenho inteiro não leva mais que isso, nem com mil assentos

/**
 * Posição de cada um dos `total` assentos, já na ordem de entrega às bancadas, e o raio de cada assento.
 * Função pura (sem DOM): as fileiras vêm da conta N ≈ k·F·(F−1), em que F é o número de fileiras.
 */
export function layout(total) {
  if (!(total > 0)) return { assentos: [], raio: 0, caixa: [0, 0, 1, 1] };
  const k = (Math.PI * (1 + FURO)) / (2 * (1 - FURO));
  const fileiras = Math.max(1, Math.round((1 + Math.sqrt(1 + (4 * total) / k)) / 2));
  const interno = fileiras === 1 ? RAIO : RAIO * FURO;
  const passo = fileiras === 1 ? 0 : (RAIO - interno) / (fileiras - 1);
  const raios = Array.from({ length: fileiras }, (_, i) => interno + i * passo);
  const soma = raios.reduce((a, b) => a + b, 0);
  // assentos por fileira, proporcionais ao raio; as sobras do arredondamento vão para quem perdeu mais
  const exatos = raios.map((r) => (total * r) / soma);
  const por = exatos.map(Math.floor);
  const faltam = total - por.reduce((a, b) => a + b, 0);
  exatos.map((x, i) => [x - Math.floor(x), i]).sort((a, b) => b[0] - a[0]).slice(0, faltam).forEach(([, i]) => por[i]++);

  let espaco = passo || Infinity;
  const assentos = [];
  raios.forEach((r, f) => {
    const n = por[f];
    if (n > 1) espaco = Math.min(espaco, (r * Math.PI) / (n - 1));
    for (let j = 0; j < n; j++) {
      const ang = n === 1 ? Math.PI / 2 : Math.PI - (Math.PI * j) / (n - 1);
      assentos.push({ x: r * Math.cos(ang), y: -r * Math.sin(ang), ang, r });
    }
  });
  assentos.sort((a, b) => b.ang - a.ang || a.r - b.r);
  const raio = Math.min(RAIO_MAXIMO, ((Number.isFinite(espaco) ? espaco : RAIO) * FOLGA) / 2);
  const lado = RAIO + raio + 1;
  return { assentos, raio, caixa: [-lado, -lado, 2 * lado, lado + raio + 1] };
}

export class Hemiciclo {
  /**
   * `unidade`: o que o número do centro conta ("vagas"); `dicaDe(grupo)`: nó da dica de uma bancada (ou null).
   * Cada grupo: `{ id, rotulo, cor, vagas }`, na ordem em que as fatias devem aparecer.
   */
  constructor({ unidade = "vagas", dicaDe = null } = {}) {
    this.unidade = unidade;
    this.dicaDe = dicaDe;
    this.total = 0;
    this.grupos = [];
    this.circulos = [];
    this.dono = [];            // por assento: índice do grupo (ou -1)
    this.realce = -1;
    this.svg = svg("svg", { class: "hemiciclo-svg", role: "img" });
    this.num = h("b", { class: "hemiciclo-num" });
    this.rotulo = h("span", { class: "hemiciclo-rotulo" });
    this.el = h("div", { class: "hemiciclo" },
      h("div", { class: "hemiciclo-caixa" }, this.svg, h("div", { class: "hemiciclo-centro", "aria-hidden": "true" }, this.num, this.rotulo)));
    this.ligar();
  }

  /** Dica e realce da bancada sob o ponteiro (mouse e caneta; no toque a tabela ao lado diz a mesma coisa). */
  ligar() {
    const sobre = (ev) => {
      if (ev.pointerType === "touch") return;
      const g = ev.target instanceof Element && ev.target.dataset.g !== undefined ? Number(ev.target.dataset.g) : -1;
      this.destacar(g);
      const grupo = this.grupos[g];
      const conteudo = grupo && this.dicaDe ? this.dicaDe(grupo) : null;
      if (conteudo) dica.mostrar(conteudo, ev.clientX, ev.clientY);
      else dica.ocultar();
    };
    this.svg.addEventListener("pointermove", sobre);
    this.svg.addEventListener("pointerleave", () => {
      this.destacar(-1);
      dica.ocultar();
    });
  }

  destacar(g) {
    if (g === this.realce) return;
    this.realce = g;
    this.circulos.forEach((c, i) => c.toggleAttribute("data-fora", g >= 0 && this.dono[i] !== g));
  }

  /** Cria os assentos do tamanho certo (só quando o total de vagas muda). */
  construir(total) {
    const { assentos, raio, caixa } = layout(total);
    this.svg.replaceChildren();
    this.svg.setAttribute("viewBox", caixa.map((v) => v.toFixed(2)).join(" "));
    const passo = Math.min(ATRASO_MS, ENTRADA_MAXIMA_MS / Math.max(1, total));
    this.circulos = assentos.map((a, i) => {
      const c = svg("circle", { class: "assento", cx: a.x.toFixed(2), cy: a.y.toFixed(2), r: raio.toFixed(2) });
      c.style.setProperty("--atraso", `${(i * passo).toFixed(0)}ms`);
      return c;
    });
    this.svg.append(...this.circulos);
    this.dono = new Array(total).fill(-2); // -2: ainda não pintado (força a primeira pintura)
    this.total = total;
    this.realce = -1;
  }

  atualizar({ total, grupos, rotulo }) {
    if (total !== this.total) this.construir(total);
    this.grupos = grupos;
    // entrega os assentos, na ordem, a quem tem vagas
    let i = 0;
    grupos.forEach((g, indice) => {
      for (let v = 0; v < g.vagas && i < total; v++, i++) this.pintar(i, indice, g.cor);
    });
    for (; i < total; i++) this.pintar(i, -1, null); // sem dono ainda
    this.num.textContent = total.toLocaleString("pt-BR");
    this.rotulo.textContent = rotulo || this.unidade;
    const lista = grupos.filter((g) => g.vagas > 0).map((g) => `${g.rotulo} ${g.vagas}`);
    this.svg.setAttribute("aria-label", `Hemiciclo com ${total} ${this.unidade}. ${lista.length ? `Bancadas: ${lista.join("; ")}.` : "Nenhuma vaga distribuída ainda."}`);
  }

  pintar(i, indice, cor) {
    if (this.dono[i] === indice && this.circulos[i].getAttribute("data-cor") === (cor || null)) return;
    const c = this.circulos[i];
    this.dono[i] = indice;
    if (cor) c.setAttribute("data-cor", cor);
    else c.removeAttribute("data-cor");
    if (indice >= 0) c.dataset.g = String(indice);
    else delete c.dataset.g;
    c.toggleAttribute("data-vazio", indice < 0);
  }
}
