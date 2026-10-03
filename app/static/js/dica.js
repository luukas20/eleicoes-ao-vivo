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

function esconder() {
  const caixa = el();
  if (caixa) caixa.hidden = true;
}

// `construir` roda a cada exibição e devolve um nó (ou null para não mostrar nada).
export function vincular(alvo, construir) {
  const mostrar = (x, y) => {
    const conteudo = construir();
    if (!conteudo) return esconder();
    const caixa = el();
    limpar(caixa).append(conteudo);
    caixa.hidden = false;
    posicionar(x, y);
  };
  alvo.addEventListener("pointerenter", (ev) => mostrar(ev.clientX, ev.clientY));
  alvo.addEventListener("pointermove", (ev) => {
    if (!el().hidden) posicionar(ev.clientX, ev.clientY);
  });
  alvo.addEventListener("pointerleave", esconder);
  alvo.addEventListener("focus", () => {
    const r = alvo.getBoundingClientRect();
    mostrar(r.left + r.width / 2, r.bottom);
  });
  alvo.addEventListener("blur", esconder);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") esconder();
  });
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
