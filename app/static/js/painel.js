// Página inicial: Presidente (Brasil) com progresso, ranking, mapa de blocos e tabela por UF.
import { Atualizador } from "./net.js";
import { Casca } from "./ui.js";
import { Avisos, Heroi, Kpis, Legenda, Mapa, Ranking, TabelaUfs, avisosDoResultado } from "./componentes.js";

const casca = new Casca();
const turno = new URLSearchParams(window.location.search).get("turno");
const consulta = turno ? `?turno=${encodeURIComponent(turno)}` : "";

const avisos = new Avisos(document.getElementById("avisos"));
const heroi = new Heroi();
const kpis = new Kpis();
const ranking = new Ranking({ metaCinquenta: true });
const mapa = new Mapa();
const legenda = new Legenda();
const tabela = new TabelaUfs({ posicoes: 2 });

document.getElementById("slot-heroi").append(heroi.el);
document.getElementById("slot-kpis").append(kpis.el);
document.getElementById("slot-ranking").append(ranking.el);
document.getElementById("slot-mapa").append(mapa.el);
document.getElementById("slot-legenda").append(legenda.el);
document.getElementById("slot-tabela").append(tabela.el);

new Atualizador({
  url: `/api/v1/presidente${consulta}`,
  aoFrescor: (f) => casca.definirFrescor(f),
  aoErro: () => casca.definirErroDeRede(),
  aoIndisponivel: (msg) => avisos.atualizar([{ tipo: "info", titulo: "Aguardando dados do TSE.", texto: msg }]),
  aoDados: (d) => {
    if (!d.disponivel) {
      avisos.atualizar([{ tipo: "info", titulo: "Aguardando o arquivo do Presidente.", texto: "O painel já está consultando o TSE." }]);
      return;
    }
    const r = d.resultado;
    casca.atualizarContexto({ fase: r.fase, turno: d.turno, turnos: d.turnos });
    avisos.atualizar(avisosDoResultado(r));
    heroi.atualizar(r);
    kpis.atualizar(r);
    ranking.atualizar(r);
    mapa.atualizar(d.ufs);
    legenda.atualizar(d.legenda);
    tabela.atualizar(d.ufs);
  },
}).iniciar();
