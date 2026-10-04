// Páginas de erro: só a casca (tema e indicador de conexão com o TSE).
import { Atualizador } from "./net.js";
import { Casca } from "./ui.js";

const casca = new Casca();
new Atualizador({
  url: "/api/v1/meta",
  intervaloMs: 15000,
  aoFrescor: (f) => casca.definirFrescor(f),
  aoErro: () => casca.definirErroDeRede(),
  aoDados: () => {},
}).iniciar();
