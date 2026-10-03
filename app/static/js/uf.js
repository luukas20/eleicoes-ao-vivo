// Página de uma UF: Presidente (na UF), Governador e Senador, em abas, e busca de municípios.
import { Atualizador } from "./net.js";
import { Casca } from "./ui.js";
import { Disputas } from "./disputas.js";
import { iniciarBusca } from "./busca.js";

const casca = new Casca();
const uf = document.body.dataset.uf;
const nomeUf = document.body.dataset.nomeUf;
const turno = new URLSearchParams(window.location.search).get("turno");
const consulta = turno ? `?turno=${encodeURIComponent(turno)}` : "";

iniciarBusca({
  uf,
  entrada: document.getElementById("busca-mun"),
  lista: document.getElementById("res-mun"),
  aviso: document.getElementById("aviso-busca"),
});

const disputas = new Disputas({
  barraAbas: document.getElementById("abas"),
  paineis: document.getElementById("paineis"),
  local: nomeUf,
  aoFase: (fase) => casca.atualizarContexto({ fase }),
});

new Atualizador({
  url: `/api/v1/uf/${uf}${consulta}`,
  aoFrescor: (f) => casca.definirFrescor(f),
  aoErro: () => casca.definirErroDeRede(),
  aoIndisponivel: () => {},
  aoDados: (dados) => {
    casca.atualizarContexto({ turno: dados.turno, turnos: dados.turnos });
    disputas.atualizar(dados.disputas);
  },
}).iniciar();
