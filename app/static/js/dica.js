// Tooltip único. Aparece no hover e também no foco por teclado, com o mesmo conteúdo.
// A dica sempre complementa: todo valor mostrado nela também está na tela ou na tabela.
import { h, limpar } from "./dom.js";

const el = () => document.getElementById("dica");

function posicionar(x, y) {
  const caixa = el();
  const margem = 12;
  const { width, height } = caixa.getBoundingClientRect();
  let esquerda = x + margem;
  let topo = y + margem;
  if (esquerda + width > window.innerWidth - 8) esquerda = Math.max(8, x - width - margem);
  if (topo + height > window.innerHeight - 8) topo = Math.max(8, y - height - margem);
  caixa.style.left = `${esquerda}px`;
  caixa.style.top = `${topo}px`;
}

/** Mostra a dica com `conteudo` (um nó) perto de (x, y) em coordenadas da janela. */
export function mostrar(conteudo, x, y) {
  const caixa = el();
  if (!caixa) return;
  limpar(caixa).append(conteudo);
  caixa.hidden = false;
  posicionar(x, y);
}

export function ocultar() {
  const caixa = el();
  if (caixa) caixa.hidden = true;
}

export function visivel() {
  const caixa = el();
  return !!caixa && !caixa.hidden;
}

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") ocultar();
});

// Tocar ou clicar num elemento focável também lhe dá foco; isso não é "foco por teclado" e não deve abrir a dica.
let ultimoPonteiro = -Infinity;
document.addEventListener("pointerdown", () => {
  ultimoPonteiro = performance.now();
}, true);
const focoVeioDoPonteiro = () => performance.now() - ultimoPonteiro < 400;

/**
 * Liga a dica a um elemento: hover (mouse/caneta) e foco por teclado. `construir` devolve um nó (ou null).
 * No toque a dica é ignorada: o toque na linha/bloco é para ler ou navegar, e o conteúdo da dica já está na tela.
 */
export function vincular(alvo, construir) {
  const exibir = (x, y) => {
    const conteudo = construir();
    if (!conteudo) return ocultar();
    mostrar(conteudo, x, y);
  };
  alvo.addEventListener("pointerenter", (ev) => {
    if (ev.pointerType !== "touch") exibir(ev.clientX, ev.clientY);
  });
  alvo.addEventListener("pointermove", (ev) => {
    if (ev.pointerType !== "touch" && visivel()) posicionar(ev.clientX, ev.clientY);
  });
  alvo.addEventListener("pointerleave", (ev) => {
    if (ev.pointerType !== "touch") ocultar();
  });
  alvo.addEventListener("focus", () => {
    if (focoVeioDoPonteiro()) return;
    const r = alvo.getBoundingClientRect();
    exibir(r.left + r.width / 2, r.bottom);
  });
  alvo.addEventListener("blur", ocultar);
}

// Linha de dica: traço colorido (a cor do candidato), valor em destaque e nome em segundo plano.
export function linha(cor, valor, nome, extra) {
  return h(
    "div",
    { class: "dica-linha" },
    h("span", { class: "chave", "data-cor": String(cor) }),
    h("b", { texto: valor }),
    h("span", { texto: nome }),
    extra ? h("span", { texto: extra }) : null,
  );
}

export function titulo(texto) {
  return h("div", { class: "dica-titulo", texto });
}
