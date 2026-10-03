// Diagnóstico: o que o painel está consultando no TSE e em que estado.
import { h, limpar } from "./dom.js";
import { Casca } from "./ui.js";
import { Atualizador } from "./net.js";
import * as fmt from "./fmt.js";

const casca = new Casca();
const raiz = document.getElementById("conteudo-status");

function tabela(cabecalho, linhas) {
  return h("div", { class: "rolagem" }, h("table", { class: "tabela" },
    h("thead", {}, h("tr", {}, ...cabecalho.map((c) => h("th", { scope: "col", texto: c })))),
    h("tbody", {}, ...linhas.map((l) => h("tr", {}, ...l.map((c) => h("td", { texto: String(c ?? "—") })))))));
}

function cartao(titulo, ...filhos) {
  return h("section", { class: "cartao" }, h("h2", { texto: titulo }), ...filhos);
}

function pintar(d) {
  const f = d.frescor;
  const c = d.poller.cliente;
  limpar(raiz).append(
    cartao("Conexão com o TSE",
      h("p", { texto: f.aguardando_primeiro_contato ? "Aguardando o primeiro contato." : `Última confirmação há ${fmt.idade(f.defasagem_s)}${f.desatualizado ? " — desatualizado" : ""}.` }),
      h("p", { class: "sub", texto: f.disjuntor.aberto ? `Disjuntor ABERTO (${f.disjuntor.motivo}); volta em ${fmt.idade(f.disjuntor.restante_s)}.` : "Disjuntor fechado: consultas liberadas." })),
    cartao("Requisições ao TSE",
      tabela(["Total", "Por segundo (10 s)", "Limite global", "Dados recebidos", "Por status", "Último erro"], [[
        fmt.inteiro(c.total), c.req_por_s, `${c.limite_req_por_s}/s`, `${(c.bytes_recebidos / 1e6).toFixed(1)} MB`,
        Object.entries(c.por_status).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—", c.ultimo_erro || "—",
      ]])),
    cartao("Arquivos acompanhados",
      h("p", { class: "sub", texto: `${d.poller.alvos} alvos · ${d.armazenamento.arquivos} arquivos carregados · ${d.poller.em_voo} em andamento` }),
      tabela(["Camada", "Alvos", "Intervalo médio"], Object.entries(d.poller.camadas).map(([k, v]) => [k, v.alvos, `${v.intervalo_medio_s} s`]))),
    cartao("Eleições",
      tabela(["Eleição", "Turno", "Cargo", "UFs", "Ciclo"], d.eleicoes.map((e) => [e.ele, e.turno, e.cargo, e.ufs, e.ciclo]))),
    cartao(`Alvos com problema (${d.poller.total_com_problema})`,
      d.poller.com_problema.length
        ? tabela(["Chave", "Status", "Erro", "Falhas"], d.poller.com_problema.map((p) => [p.chave, p.status, p.erro, p.falhas]))
        : h("p", { class: "sub", texto: "Nenhum." })),
  );
}

new Atualizador({
  url: "/api/v1/status",
  intervaloMs: 5000,
  aoFrescor: (f) => casca.definirFrescor(f),
  aoErro: () => casca.definirErroDeRede(),
  aoDados: pintar,
}).iniciar();
