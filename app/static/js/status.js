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

const pico = (p) => (p.n ? `${fmt.inteiro(p.n)} (${fmt.dataHora(p.em)})` : "—");

/** Quadro de acessos: pelo link público e total, com os picos. Os números vêm do próprio painel (sem guardar IP). */
function quadroAcessos(a) {
  const linha = (rotulo, f) => [rotulo, f(a.link), f(a.todos)];
  return cartao("Acessos ao painel",
    h("p", { class: "sub", texto: `Contando desde ${fmt.dataHora(a.desde)}. "Todos" inclui também este computador e a rede local. "Pessoas online" são aparelhos que consultaram o painel nos últimos ${a.janela_online_s} s (aproximado; o painel não guarda IP).` }),
    tabela(["Medida", "Pelo link público", "Todos"], [
      linha("Páginas abertas (visitas)", (e) => fmt.inteiro(e.paginas)),
      linha("Pessoas online agora", (e) => fmt.inteiro(e.online)),
      linha("Pico de pessoas online", (e) => pico(e.pico_online)),
      linha("Requisições (total)", (e) => fmt.inteiro(e.requisicoes)),
      linha("Requisições por minuto (agora)", (e) => fmt.inteiro(e.req_por_min)),
      linha("Pico de requisições por minuto", (e) => pico(e.pico_req_por_min)),
      linha("Requisições em andamento (agora)", (e) => fmt.inteiro(e.em_andamento)),
      linha("Pico de requisições em andamento", (e) => pico(e.pico_em_andamento)),
    ]));
}

function pintar(d) {
  const f = d.frescor;
  const c = d.poller.cliente;
  limpar(raiz).append(
    cartao("Conexão com o TSE",
      h("p", { texto: f.aguardando_primeiro_contato ? "Aguardando o primeiro contato." : `Última confirmação há ${fmt.idade(f.defasagem_s)}${f.desatualizado ? " — desatualizado" : ""}.` }),
      h("p", { class: "sub", texto: f.disjuntor.aberto ? `Disjuntor ABERTO (${f.disjuntor.motivo}); volta em ${fmt.idade(f.disjuntor.restante_s)}.` : "Disjuntor fechado: consultas liberadas." })),
    quadroAcessos(d.acessos),
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
