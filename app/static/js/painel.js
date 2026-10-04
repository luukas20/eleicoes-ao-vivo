// Página inicial: Presidente (Brasil) com placar, mapa das UFs, ranking, evolução e tabela por UF.
import { Atualizador } from "./net.js";
import { Casca } from "./ui.js";
import { Avisos, Heroi, Kpis, Legenda, Ranking, TabelaUfs, avisosDoResultado } from "./componentes.js";
import { MapaUfs } from "./mapa.js";
import { GraficoEvolucao } from "./grafico.js";
import { Placar } from "./placar.js";

const casca = new Casca();
const turno = new URLSearchParams(window.location.search).get("turno");
const consulta = turno ? `?turno=${encodeURIComponent(turno)}` : "";

const avisos = new Avisos(document.getElementById("avisos"));
const placar = new Placar({ rotulo: "Presidente · Brasil", nivel: 1, metaCinquenta: true });
const heroi = new Heroi();
const kpis = new Kpis();
const ranking = new Ranking({ metaCinquenta: true });
const mapa = new MapaUfs();
const legenda = new Legenda();
const tabela = new TabelaUfs({ posicoes: 2 });

document.getElementById("slot-placar").append(placar.el);
document.getElementById("slot-heroi").append(heroi.el);
document.getElementById("slot-kpis").append(kpis.el);
document.getElementById("slot-ranking").append(ranking.el);
document.getElementById("slot-mapa").append(mapa.el);
document.getElementById("slot-seletor").append(mapa.seletor);
document.getElementById("slot-legenda").append(legenda.el);
document.getElementById("slot-tabela").append(tabela.el);

const grafico = new GraficoEvolucao({
  url: `/api/v1/historico/presidente/br${consulta}`,
  titulo: "Evolução do percentual dos três primeiros",
  metaCinquenta: true,
});
document.getElementById("slot-grafico").append(grafico.el);
grafico.definirAtivo(true);

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
    placar.kicker.textContent = `Presidente · Brasil${d.turno === 2 ? " · 2º turno" : ""}`;
    avisos.atualizar(avisosDoResultado(r));
    placar.atualizar(r);
    heroi.atualizar(r);
    kpis.atualizar(r);
    ranking.atualizar(r);
    mapa.atualizar(d.ufs);
    legenda.atualizar(d.ufs);
    tabela.atualizar(d.ufs);
    // o título da aba mostra o andamento: dá para acompanhar de outra janela
    document.title = `${r.secoes.st > 0 && r.secoes.pst ? `${r.secoes.pst.t}% apurado · ` : ""}Presidente · Eleições 2026 ao Vivo`;
  },
}).iniciar();
