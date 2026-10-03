// Página de um município: Presidente, Governador e Senador no município.
// O servidor só passa a consultar o TSE para este município quando alguém o abre (e por ~90 s depois).
import { Atualizador } from "./net.js";
import { Casca } from "./ui.js";
import { Avisos } from "./componentes.js";
import { Disputas } from "./disputas.js";

const casca = new Casca();
const { uf, nomeUf, codigo } = document.body.dataset;
const turno = new URLSearchParams(window.location.search).get("turno");
const consulta = turno ? `?turno=${encodeURIComponent(turno)}` : "";

const avisoGeral = new Avisos(document.getElementById("avisos"));
const titulo = document.getElementById("titulo-municipio");
const migalha = document.getElementById("nome-municipio");
let disputas = null;
let aguardando = true;

const atualizador = new Atualizador({
  url: `/api/v1/municipio/${uf}/${codigo}${consulta}`,
  aoFrescor: (f) => casca.definirFrescor(f),
  aoErro: () => casca.definirErroDeRede(),
  // 404 = município inexistente nesta UF (não adianta repetir); 503 = lista ainda carregando ou muitos
  // acompanhamentos ao mesmo tempo (tenta de novo em instantes)
  aoIndisponivel: (msg, status) => {
    avisoGeral.atualizar([{ tipo: status === 404 ? "atencao" : "info", titulo: "Município indisponível.", texto: msg }]);
    if (status !== 404) atualizador.buscarEm(5000);
  },
  // enquanto algum arquivo do município não chegou, consulta a cada 2 s (depois volta ao ritmo normal)
  aoSemMudanca: () => {
    if (aguardando) atualizador.buscarEm(2000);
  },
  aoDados: (d) => {
    avisoGeral.atualizar([]);
    const nome = d.municipio.nome;
    titulo.textContent = nome;
    migalha.textContent = nome;
    document.title = `${nome} (${nomeUf}) · Eleições ao Vivo`;
    casca.atualizarContexto({ turno: d.turno, turnos: d.turnos });
    disputas ??= new Disputas({
      barraAbas: document.getElementById("abas"),
      paineis: document.getElementById("paineis"),
      local: nome,
      aoFase: (fase) => casca.atualizarContexto({ fase }),
    });
    aguardando = disputas.atualizar(d.disputas);
    if (aguardando) atualizador.buscarEm(2000);
  },
});
atualizador.iniciar();
