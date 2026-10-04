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

/** Reinicia o lampejo discreto que marca um número que acabou de mudar. */
export function piscar(el) {
  el.classList.remove("mudou");
  void el.offsetWidth; // força o navegador a reiniciar a animação
  el.classList.add("mudou");
}

/** Atualiza o texto e, se mudou de verdade (a primeira pintura não conta), faz o lampejo. */
export function definirTexto(el, texto) {
  const antes = el.textContent;
  if (antes === texto) return;
  el.textContent = texto;
  if (antes !== "") piscar(el);
}

/** Texto com ponto de quebra depois de cada "/" (siglas de federação: "PRD/SOLIDARIEDADE"), para caber em colunas estreitas. */
export function quebravel(texto) {
  const partes = String(texto ?? "").split("/");
  return partes.flatMap((parte, i) => (i < partes.length - 1 ? [`${parte}/`, document.createElement("wbr")] : [parte]));
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
  mapa: ['<path d="M9 4L3 6.5v13L9 17l6 2.5 6-2.5v-13L15 7 9 4z"/>', '<path d="M9 4v13M15 7v12.5"/>'],
  linhas: ['<path d="M3 17l5-6 4 3 8-9"/>', '<path d="M3 21h18"/>'],
  tabela: ['<rect x="3.5" y="4.5" width="17" height="15" rx="2.2"/>', '<path d="M3.5 10h17M3.5 15h17M9.5 4.5v15"/>'],
  blocos: ['<rect x="3.5" y="3.5" width="7" height="7" rx="1.8"/>', '<rect x="13.5" y="3.5" width="7" height="7" rx="1.8"/>',
    '<rect x="3.5" y="13.5" width="7" height="7" rx="1.8"/>', '<rect x="13.5" y="13.5" width="7" height="7" rx="1.8"/>'],
};

/**
 * Controle segmentado (escolha de uma entre poucas opções), com um indicador que desliza até a opção ativa.
 * `opcoes`: [{ valor, texto, icone? }]. Cada botão tem `aria-pressed`; `definir(valor)` troca a opção sem disparar `aoEscolher`.
 */
export function segmentado({ rotulo, opcoes, ativo, aoEscolher }) {
  const botoes = opcoes.map((o) => h("button", { type: "button", dados: { valor: o.valor }, onclick: () => aoEscolher(o.valor) },
    o.icone ? icone(o.icone) : null, h("span", { texto: o.texto })));
  const el = h("div", { class: "seg", role: "group", "aria-label": rotulo }, ...botoes);
  el.style.setProperty("--n", String(opcoes.length));
  const definir = (valor) => {
    botoes.forEach((b, i) => {
      const ligado = b.dataset.valor === valor;
      b.setAttribute("aria-pressed", String(ligado));
      if (ligado) el.style.setProperty("--i", String(i));
    });
  };
  definir(ativo);
  return { el, botoes, definir };
}

export function icone(nome) {
  const el = svg("svg", {
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false",
  });
  // conteúdo estático e confiável (definido acima), nunca derivado de dados externos
  el.innerHTML = (TRACOS[nome] || []).join("");
  return el;
}
