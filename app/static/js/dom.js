// Construção de DOM sem innerHTML: todo texto entra por textContent/createTextNode,
// porque nomes e valores vêm de arquivos externos e não podem ser interpretados como HTML.

export function h(tag, attrs = {}, ...filhos) {
  const el = document.createElement(tag);
  for (const [chave, valor] of Object.entries(attrs || {})) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (chave === "class") el.className = valor;
    else if (chave === "texto") el.textContent = valor;
    else if (chave === "dados") Object.assign(el.dataset, valor);
    else if (chave.startsWith("on") && typeof valor === "function") el.addEventListener(chave.slice(2), valor);
    else el.setAttribute(chave, valor === true ? "" : String(valor));
  }
  anexar(el, filhos);
  return el;
}

export function anexar(el, filhos) {
  for (const filho of filhos.flat(Infinity)) {
    if (filho === null || filho === undefined || filho === false) continue;
    el.append(filho instanceof Node ? filho : document.createTextNode(String(filho)));
  }
  return el;
}

export function limpar(el) {
  el.replaceChildren();
  return el;
}

const SVG_NS = "http://www.w3.org/2000/svg";

export function svg(tag, attrs = {}, ...filhos) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [chave, valor] of Object.entries(attrs)) el.setAttribute(chave, String(valor));
  for (const filho of filhos) el.append(filho);
  return el;
}

// Ícones de traço (24x24), herdam a cor do texto. Sempre acompanham um rótulo de texto.
const TRACOS = {
  ok: ['<circle cx="12" cy="12" r="9"/>', '<path d="M8 12.5l2.7 2.7L16 9.5"/>'],
  info: ['<circle cx="12" cy="12" r="9"/>', '<path d="M12 11v5"/>', '<path d="M12 8h.01"/>'],
  alerta: ['<path d="M12 3.5l9.5 16.5h-19z"/>', '<path d="M12 10v4"/>', '<path d="M12 17h.01"/>'],
  erro: ['<circle cx="12" cy="12" r="9"/>', '<path d="M9 9l6 6M15 9l-6 6"/>'],
  lua: ['<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>'],
  sol: ['<circle cx="12" cy="12" r="4"/>', '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'],
  ponto: ['<circle class="pulso" cx="12" cy="12" r="5" fill="currentColor" stroke="none"/>'],
};

export function icone(nome) {
  const el = svg("svg", {
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false",
  });
  // conteúdo estático e confiável (definido acima), nunca derivado de dados externos
  el.innerHTML = (TRACOS[nome] || []).join("");
  return el;
}
