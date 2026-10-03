// Governadores / Senadores: uma linha por UF, com os primeiros colocados.
import { Atualizador } from "./net.js";
import { Casca } from "./ui.js";
import { Avisos, TabelaUfs } from "./componentes.js";

const casca = new Casca();
const slug = document.body.dataset.slug;
const turno = new URLSearchParams(window.location.search).get("turno");
const consulta = turno ? `?turno=${encodeURIComponent(turno)}` : "";

const avisos = new Avisos(document.getElementById("avisos"));
const senado = slug === "senador";
const tabela = new TabelaUfs({ posicoes: senado ? 3 : 2, vagas: senado ? 2 : 1, semCor: true });
document.getElementById("slot-tabela").append(tabela.el);
const resumo = document.getElementById("resumo");

let contexto = { fase: null, turno: null, turnos: [], data: null };
const aplicarContexto = (parcial) => {
  contexto = { ...contexto, ...parcial };
  casca.definirContexto(contexto);
};
fetch("/api/v1/meta").then((r) => r.json()).then((m) => aplicarContexto({ fase: m.fase, data: m.data })).catch(() => {});

new Atualizador({
  url: `/api/v1/cargo/${slug}${consulta}`,
  aoFrescor: (f) => casca.definirFrescor(f),
  aoErro: () => casca.definirErroDeRede(),
  aoIndisponivel: (msg) => avisos.atualizar([{ tipo: "info", titulo: "Aguardando dados do TSE.", texto: msg }]),
  aoDados: (d) => {
    aplicarContexto({ turno: d.turno, turnos: d.turnos });
    avisos.atualizar([]);
    tabela.atualizar(d.linhas);
    const disponiveis = d.linhas.filter((l) => l.disponivel);
    const iniciadas = disponiveis.filter((l) => l.andamento !== "n").length;
    const finais = disponiveis.filter((l) => l.final || l.andamento === "f").length;
    resumo.textContent = `${iniciadas} de ${d.linhas.length} UFs com apuração iniciada · ${finais} com totalização finalizada`
      + (d.vagas > 1 ? ` · ${d.vagas} vagas por UF` : "");
  },
}).iniciar();
