// Abas com as disputas de um local (UF ou município): Presidente, Governador, Senador.
// Cada disputa tem avisos, placar, andamento, indicadores e ranking, criados uma vez e atualizados a cada dado novo.
import { h } from "./dom.js";
import { Avisos, Heroi, Kpis, Ranking, avisosDoResultado } from "./componentes.js";
import { GraficoEvolucao } from "./grafico.js";
import { PainelProporcional } from "./deputados.js";
import { Placar } from "./placar.js";

const secao = (titulo, ...conteudo) => {
  const id = `sec-${Math.random().toString(36).slice(2, 8)}`;
  return h("section", { class: "sec", "aria-labelledby": id },
    h("header", { class: "sec-cab" }, h("h2", { class: "sec-tit", id, texto: titulo })), ...conteudo);
};

export class Disputas {
  /**
   * `local`: nome mostrado nos títulos (ex.: "São Paulo"); `aoFase`: chamado com a fase (o|s) de cada resultado;
   * `historico`: `{ uf, consulta }` para incluir o gráfico de evolução de cada disputa (só existe para UFs).
   * `proporcional`: `{ uf, turno, aoFrescor, aoErro }` liga as abas dos deputados (cada uma consulta a própria API).
   */
  constructor({ barraAbas, paineis, local, aoFase, historico = null, proporcional = null }) {
    this.barraAbas = barraAbas;
    this.paineis = paineis;
    this.local = local;
    this.aoFase = aoFase;
    this.historico = historico;
    this.proporcional = proporcional;
    this.itens = new Map(); // slug -> { botao, painel, ativar, ...componentes da disputa }
    this.selecionada = window.location.hash.replace("#", "") || null;
  }

  selecionar(slug) {
    if (!slug) return;
    this.selecionada = slug;
    for (const [s, d] of this.itens) {
      const ativa = s === slug;
      d.botao.setAttribute("aria-selected", String(ativa));
      d.painel.hidden = !ativa;
      d.ativar?.(ativa); // gráficos e painéis de deputados de abas ocultas não consultam a API
    }
    history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${slug}`);
  }

  garantir(disputa) {
    let d = this.itens.get(disputa.slug);
    if (d) return d;
    const majoritaria = disputa.slug !== "senador";
    const avisos = new Avisos(h("div", { class: "avisos", "aria-live": "polite" }));
    const placar = new Placar({ rotulo: `${disputa.nome} · ${this.local}`, nivel: 2, metaCinquenta: majoritaria });
    const heroi = new Heroi({ rotulo: "Seções totalizadas" });
    const kpis = new Kpis();
    const ranking = new Ranking({ metaCinquenta: majoritaria, corte: !majoritaria });
    const grafico = this.historico
      ? new GraficoEvolucao({
        url: `/api/v1/historico/${disputa.slug}/${this.historico.uf}${this.historico.consulta}`,
        titulo: `Evolução · ${disputa.nome}`,
        metaCinquenta: majoritaria,
      })
      : null;
    const blocoRanking = secao("Todos os candidatos", ranking.el);
    const painel = h("section", { id: `painel-${disputa.slug}`, role: "tabpanel", class: "grade-pagina painel-disputa", hidden: true },
      avisos.raiz,
      h("div", { class: "abertura abertura--uf" }, h("div", { class: "abertura-esq" }, placar.el, heroi.el), secao("Eleitorado", kpis.el)),
      grafico ? h("div", { class: "duas-colunas" }, blocoRanking, grafico.el) : blocoRanking);
    const botao = h("button", {
      type: "button", role: "tab", "aria-controls": painel.id, "aria-selected": "false", texto: disputa.nome,
      onclick: () => this.selecionar(disputa.slug),
    });
    this.barraAbas.append(botao);
    this.paineis.append(painel);
    d = { botao, painel, avisos, placar, heroi, kpis, ranking, grafico, ativar: grafico ? (ativa) => grafico.definirAtivo(ativa) : null };
    this.itens.set(disputa.slug, d);
    return d;
  }

  /** Aba de um cargo proporcional (Deputado Federal, Estadual ou Distrital): o painel busca os próprios dados. */
  garantirProporcional(cargo) {
    let d = this.itens.get(cargo.slug);
    if (d) return d;
    const { uf, turno, aoFrescor, aoErro } = this.proporcional;
    const painel = new PainelProporcional({ slug: cargo.slug, nome: cargo.nome, uf, nomeUf: this.local, turno, aoFrescor, aoErro, aoFase: this.aoFase });
    const botao = h("button", {
      type: "button", role: "tab", "aria-controls": painel.el.id, "aria-selected": "false", texto: cargo.nome,
      onclick: () => this.selecionar(cargo.slug),
    });
    this.barraAbas.append(botao);
    this.paineis.append(painel.el);
    d = { botao, painel: painel.el, ativar: (ativa) => painel.definirAtivo(ativa) };
    this.itens.set(cargo.slug, d);
    return d;
  }

  /** Devolve true se alguma disputa ainda está aguardando o primeiro arquivo do TSE. `proporcionais`: cargos de deputado da UF. */
  atualizar(disputas, proporcionais = []) {
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
      d.placar.atualizar(r);
      d.heroi.atualizar(r);
      d.kpis.atualizar(r);
      d.ranking.atualizar(r);
    }
    if (this.proporcional) for (const cargo of proporcionais) this.garantirProporcional(cargo);
    if (!this.selecionada || !this.itens.has(this.selecionada)) this.selecionar(disputas.length ? disputas[0].slug : proporcionais[0]?.slug);
    else this.selecionar(this.selecionada);
    return aguardando;
  }
}
