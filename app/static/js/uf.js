// Página de uma UF: Presidente (na UF), Governador e Senador, em abas.
import { h } from "./dom.js";
import { Atualizador } from "./net.js";
import { Casca } from "./ui.js";
import { Avisos, Heroi, Kpis, Ranking, avisosDoResultado } from "./componentes.js";

const casca = new Casca();
const uf = document.body.dataset.uf;
const nomeUf = document.body.dataset.nomeUf;
const turno = new URLSearchParams(window.location.search).get("turno");
const consulta = turno ? `?turno=${encodeURIComponent(turno)}` : "";

const barraAbas = document.getElementById("abas");
const paineis = document.getElementById("paineis");
const disputas = new Map(); // slug -> { botao, painel, avisos, heroi, kpis, ranking }
let selecionada = window.location.hash.replace("#", "") || null;

let contexto = { fase: null, turno: null, turnos: [], data: null };
const aplicarContexto = (parcial) => {
  contexto = { ...contexto, ...parcial };
  casca.definirContexto(contexto);
};
fetch("/api/v1/meta").then((r) => r.json()).then((m) => aplicarContexto({ fase: m.fase, data: m.data })).catch(() => {});

function selecionar(slug) {
  if (!slug) return;
  selecionada = slug;
  for (const [s, d] of disputas) {
    const ativa = s === slug;
    d.botao.setAttribute("aria-selected", String(ativa));
    d.painel.hidden = !ativa;
  }
  history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${slug}`);
}

function garantir(disputa) {
  let d = disputas.get(disputa.slug);
  if (d) return d;
  const avisos = new Avisos(h("div", { class: "avisos", "aria-live": "polite" }));
  const heroi = new Heroi({ rotulo: `${disputa.nome} · seções totalizadas` });
  const kpis = new Kpis();
  const ranking = new Ranking({ metaCinquenta: disputa.slug !== "senador", corte: disputa.slug === "senador" });
  const painel = h("section", { id: `painel-${disputa.slug}`, role: "tabpanel", class: "grade-pagina", hidden: true },
    avisos.raiz, heroi.el, kpis.el,
    h("section", { class: "cartao" }, h("h2", { texto: `${disputa.nome} · ${nomeUf}` }), ranking.el));
  const botao = h("button", { type: "button", role: "tab", "aria-controls": painel.id, "aria-selected": "false", texto: disputa.nome, onclick: () => selecionar(disputa.slug) });
  barraAbas.append(botao);
  paineis.append(painel);
  d = { botao, painel, avisos, heroi, kpis, ranking };
  disputas.set(disputa.slug, d);
  return d;
}

new Atualizador({
  url: `/api/v1/uf/${uf}${consulta}`,
  aoFrescor: (f) => casca.definirFrescor(f),
  aoErro: () => casca.definirErroDeRede(),
  aoIndisponivel: () => {},
  aoDados: (dados) => {
    aplicarContexto({ turno: dados.turno, turnos: dados.turnos });
    for (const disputa of dados.disputas) {
      const d = garantir(disputa);
      if (!disputa.disponivel) {
        d.avisos.atualizar([{ tipo: "info", titulo: "Aguardando dados do TSE.", texto: "" }]);
        continue;
      }
      const r = disputa.resultado;
      aplicarContexto({ fase: r.fase });
      d.avisos.atualizar(avisosDoResultado(r));
      d.heroi.atualizar(r);
      d.kpis.atualizar(r);
      d.ranking.atualizar(r);
    }
    if (!selecionada || !disputas.has(selecionada)) selecionar(dados.disputas.length ? dados.disputas[0].slug : null);
    else selecionar(selecionada);
  },
}).iniciar();
