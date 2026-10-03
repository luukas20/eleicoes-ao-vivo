// Abas com as disputas de um local (UF ou município): Presidente, Governador, Senador.
// Cada disputa tem avisos, progresso, KPIs e ranking, criados uma vez e atualizados a cada dado novo.
import { h } from "./dom.js";
import { Avisos, Heroi, Kpis, Ranking, avisosDoResultado } from "./componentes.js";
import { GraficoEvolucao } from "./grafico.js";

export class Disputas {
  /**
   * `local`: nome mostrado nos títulos (ex.: "São Paulo"); `aoFase`: chamado com a fase (o|s) de cada resultado;
   * `historico`: `{ uf, consulta }` para incluir o gráfico de evolução de cada disputa (só existe para UFs).
   */
  constructor({ barraAbas, paineis, local, aoFase, historico = null }) {
    this.barraAbas = barraAbas;
    this.paineis = paineis;
    this.local = local;
    this.aoFase = aoFase;
    this.historico = historico;
    this.itens = new Map(); // slug -> { botao, painel, avisos, heroi, kpis, ranking }
    this.selecionada = window.location.hash.replace("#", "") || null;
  }

  selecionar(slug) {
    if (!slug) return;
    this.selecionada = slug;
    for (const [s, d] of this.itens) {
      const ativa = s === slug;
      d.botao.setAttribute("aria-selected", String(ativa));
      d.painel.hidden = !ativa;
      d.grafico?.definirAtivo(ativa); // gráficos de abas ocultas não consultam a API
    }
    history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${slug}`);
  }

  garantir(disputa) {
    let d = this.itens.get(disputa.slug);
    if (d) return d;
    const avisos = new Avisos(h("div", { class: "avisos", "aria-live": "polite" }));
    const heroi = new Heroi({ rotulo: `${disputa.nome} · seções totalizadas` });
    const kpis = new Kpis();
    const ranking = new Ranking({ metaCinquenta: disputa.slug !== "senador", corte: disputa.slug === "senador" });
    const grafico = this.historico
      ? new GraficoEvolucao({
        url: `/api/v1/historico/${disputa.slug}/${this.historico.uf}${this.historico.consulta}`,
        titulo: `Evolução · ${disputa.nome}`,
        metaCinquenta: disputa.slug !== "senador",
      })
      : null;
    const painel = h("section", { id: `painel-${disputa.slug}`, role: "tabpanel", class: "grade-pagina", hidden: true },
      avisos.raiz, heroi.el, kpis.el,
      h("section", { class: "cartao" }, h("h2", { texto: `${disputa.nome} · ${this.local}` }), ranking.el),
      grafico ? grafico.el : null);
    const botao = h("button", {
      type: "button", role: "tab", "aria-controls": painel.id, "aria-selected": "false", texto: disputa.nome,
      onclick: () => this.selecionar(disputa.slug),
    });
    this.barraAbas.append(botao);
    this.paineis.append(painel);
    d = { botao, painel, avisos, heroi, kpis, ranking, grafico };
    this.itens.set(disputa.slug, d);
    return d;
  }

  /** Devolve true se alguma disputa ainda está aguardando o primeiro arquivo do TSE. */
  atualizar(disputas) {
    let aguardando = false;
    for (const disputa of disputas) {
      const d = this.garantir(disputa);
      if (!disputa.disponivel) {
        aguardando = true;
        d.avisos.atualizar([{ tipo: "info", titulo: "Aguardando dados do TSE.", texto: "A consulta a este local começou agora." }]);
        continue;
      }
      const r = disputa.resultado;
      this.aoFase?.(r.fase);
      d.avisos.atualizar(avisosDoResultado(r));
      d.heroi.atualizar(r);
      d.kpis.atualizar(r);
      d.ranking.atualizar(r);
    }
    if (!this.selecionada || !this.itens.has(this.selecionada)) this.selecionar(disputas.length ? disputas[0].slug : null);
    else this.selecionar(this.selecionada);
    return aguardando;
  }
}
