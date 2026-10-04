// Deputados Federais e Estaduais, visão nacional: composição em hemiciclo, bancadas somadas, mapa e uma linha por UF.
import { Atualizador } from "./net.js";
import { Casca } from "./ui.js";
import { h } from "./dom.js";
import { Avisos, Heroi, Legenda } from "./componentes.js";
import { MapaUfs } from "./mapa.js";
import { Composicao, TabelaBancadas, TabelaUfsProporcional, manchetePropor, ordemBancada } from "./deputados.js";

const casca = new Casca();
const slug = document.body.dataset.slug;
const turno = new URLSearchParams(window.location.search).get("turno");
const consulta = turno ? `?turno=${encodeURIComponent(turno)}` : "";
const cargo = slug === "deputado-federal" ? "Deputado Federal" : "Deputado Estadual";

const avisos = new Avisos(document.getElementById("avisos"));
const kicker = h("p", { class: "kicker", texto: `${cargo} · Brasil` });
const titulo = h("h1", { class: "manchete", texto: "Carregando a apuração…" });
const sub = h("p", { class: "manchete-sub", hidden: true });
const heroi = new Heroi({ rotulo: "Seções totalizadas · soma das UFs" });
const composicao = new Composicao();
const bancadas = new TabelaBancadas({ nacional: true });
const mapa = new MapaUfs({ porPartido: true, quem: "do partido ou federação mais votado" });
const legenda = new Legenda({ porPartido: true, lista: true });
const tabela = new TabelaUfsProporcional();

document.getElementById("slot-manchete").append(h("div", { class: "placar" }, kicker, titulo, sub));
document.getElementById("slot-heroi").append(heroi.el);
document.getElementById("slot-composicao").append(composicao.el);
document.getElementById("slot-bancadas").append(bancadas.el);
document.getElementById("slot-mapa").append(mapa.el);
document.getElementById("slot-seletor").append(mapa.seletor);
document.getElementById("slot-legenda").append(legenda.el);
document.getElementById("slot-tabela").append(tabela.el);

const soma = (lista, campo) => lista.reduce((t, u) => t + (u.secoes[campo] || 0), 0);

new Atualizador({
  url: `/api/v1/proporcional/${slug}${consulta}`,
  aoFrescor: (f) => casca.definirFrescor(f),
  aoErro: () => casca.definirErroDeRede(),
  aoIndisponivel: (msg) => avisos.atualizar([{ tipo: "info", titulo: "Aguardando dados do TSE.", texto: msg }]),
  aoDados: (d) => {
    casca.atualizarContexto({ turno: d.turno, turnos: d.turnos });
    avisos.atualizar([]);
    const disponiveis = d.ufs.filter((u) => u.disponivel);
    const iniciadas = disponiveis.filter((u) => u.andamento !== "n");
    const finais = disponiveis.filter((u) => u.final || u.andamento === "f");
    const faltam = d.ufs.length - disponiveis.length;
    const grupos = [...d.distribuicao].sort(ordemBancada);
    const iniciou = iniciadas.length > 0 && grupos.some((g) => g.votos > 0);
    const final = d.ufs.length > 0 && finais.length === d.ufs.length;

    const m = manchetePropor({
      cargo, total: d.vagas_total, grupos, divulga: disponiveis.some((u) => u.divulga), iniciou, final,
      textoFinal: "Totalização final concluída em todas as UFs.",
    });
    titulo.textContent = m.titulo;
    sub.textContent = m.sub;
    sub.hidden = !m.sub;
    kicker.textContent = `${cargo} · Brasil${d.turno === 2 ? " · 2º turno" : ""}`;

    let nota;
    if (faltam) nota = `${faltam} ${faltam === 1 ? "UF ainda sem dados" : "UFs ainda sem dados"} do TSE: as vagas ${faltam === 1 ? "dela" : "delas"} ainda não entram na conta.`;
    else if (final) nota = "Totalização final concluída em todas as UFs: as vagas são as definitivas.";
    else if (iniciou) nota = `${iniciadas.length} de ${d.ufs.length} UFs com apuração iniciada. Vagas conforme o TSE publica durante a apuração; mudam até a totalização final de cada UF.`;
    else nota = "As vagas aparecem distribuídas aqui assim que a apuração começar.";
    composicao.atualizar({ total: d.vagas_total, grupos, nota });
    bancadas.atualizar(grupos, { total: d.vagas_total, iniciou });
    mapa.atualizar(d.ufs);
    legenda.atualizar(d.ufs);
    tabela.atualizar(d.ufs);

    // andamento nacional: soma das seções das UFs (conta do painel)
    const ts = soma(disponiveis, "ts");
    const st = soma(disponiveis, "st");
    const n = ts ? (100 * st) / ts : 0;
    const ultima = disponiveis.map((u) => u.totalizado_em).filter(Boolean).sort().at(-1) || null;
    heroi.atualizar({ secoes: { ts, st, pst: { t: n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }), n } }, totalizado_em: ultima });
    document.title = `${st > 0 ? `${n.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}% apurado · ` : ""}${cargo} · Eleições 2026 ao Vivo`;
  },
}).iniciar();
