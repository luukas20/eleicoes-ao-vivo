// "Casca" comum a todas as páginas: tema, indicador de conexão com o TSE, faixa de dados simulados,
// subtítulo do topo, seletor de UF e troca de turno.
import { h, icone, limpar } from "./dom.js";
import * as fmt from "./fmt.js";

function temaAtual() {
  const forcado = document.documentElement.getAttribute("data-tema");
  if (forcado) return forcado;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "escuro" : "claro";
}

function iniciarTema() {
  const botao = document.getElementById("btn-tema");
  if (!botao) return;
  const pintar = () => {
    const escuro = temaAtual() === "escuro";
    limpar(botao).append(icone(escuro ? "sol" : "lua"));
    botao.setAttribute("aria-label", escuro ? "Usar tema claro" : "Usar tema escuro");
    botao.title = botao.getAttribute("aria-label");
  };
  botao.addEventListener("click", () => {
    const proximo = temaAtual() === "escuro" ? "claro" : "escuro";
    document.documentElement.setAttribute("data-tema", proximo);
    try {
      localStorage.setItem("tema", proximo);
    } catch (e) {
      /* sem armazenamento: vale só nesta visita */
    }
    pintar();
  });
  pintar();
}

export class Casca {
  constructor() {
    this.chip = document.getElementById("chip-status");
    this.faixa = document.getElementById("faixa-simulado");
    this.sub = document.getElementById("sub-topo");
    this.frescor = null;
    this.erroDeRede = false;
    iniciarTema();
    this.iniciarSeletorUf();
    this.pintarChip();
    setInterval(() => this.pintarChip(), 1000);
  }

  iniciarSeletorUf() {
    const sel = document.getElementById("sel-uf");
    if (!sel) return;
    sel.addEventListener("change", () => {
      if (sel.value) window.location.href = `/uf/${sel.value}${window.location.search}`;
    });
  }

  definirFrescor(frescor) {
    this.frescor = frescor;
    this.erroDeRede = false;
    this.pintarChip();
  }

  definirErroDeRede() {
    this.erroDeRede = true;
    this.pintarChip();
  }

  definirContexto({ fase, turno, turnos, data }) {
    if (this.faixa) this.faixa.hidden = fase !== "s";
    if (this.sub) {
      const partes = [fmt.turnoPorExtenso(turno), fmt.dataLonga(data)].filter(Boolean);
      this.sub.textContent = partes.join(" · ");
    }
    this.montarTurnos(turno, turnos || []);
  }

  montarTurnos(atual, turnos) {
    const caixa = document.getElementById("turnos");
    if (!caixa) return;
    limpar(caixa);
    caixa.hidden = turnos.length < 2;
    for (const t of turnos) {
      const url = new URL(window.location.href);
      url.searchParams.set("turno", String(t));
      caixa.append(h("a", { href: url.pathname + url.search, "aria-current": t === atual ? "true" : null, texto: `${t}º turno` }));
    }
  }

  pintarChip() {
    if (!this.chip) return;
    let estado = "atencao";
    let icon = "alerta";
    let texto = "Conectando…";
    const f = this.frescor;
    if (this.erroDeRede) {
      [estado, icon, texto] = ["critico", "erro", "Sem conexão com o servidor do painel"];
    } else if (f) {
      const decorrido = (performance.now() - f.recebidoEm) / 1000;
      const idade = f.defasagemS === null ? null : f.defasagemS + decorrido;
      if (f.disjuntor) {
        [estado, icon, texto] = ["critico", "erro", "Consultas ao TSE pausadas"];
      } else if (idade === null) {
        [estado, icon, texto] = ["atencao", "alerta", "Aguardando o primeiro contato com o TSE"];
      } else if (f.desatualizado) {
        [estado, icon, texto] = ["grave", "alerta", `Sem atualização do TSE há ${fmt.idade(idade)}`];
      } else {
        [estado, icon, texto] = ["ok", "ponto", `Ao vivo · atualizado há ${fmt.idade(idade)}`];
      }
    }
    this.chip.dataset.estado = estado;
    limpar(this.chip).append(icone(icon), h("span", { texto }));
  }
}
