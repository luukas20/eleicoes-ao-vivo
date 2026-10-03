// Busca de municípios de uma UF pelo nome. Os resultados são links comuns para a página do município.
import { h, limpar } from "./dom.js";

export function iniciarBusca({ uf, entrada, lista, aviso }) {
  if (!entrada || !lista) return;
  let temporizador = null;
  let sequencia = 0; // descarta respostas que chegam fora de ordem

  const mostrar = (itens, mensagem) => {
    limpar(lista);
    for (const m of itens) {
      lista.append(
        h("li", {}, h("a", { href: `/municipio/${uf}/${m.cd}${window.location.search}` }, m.nome,
          m.capital ? h("span", { class: "sub", texto: " · capital" }) : null)),
      );
    }
    lista.hidden = itens.length === 0;
    aviso.textContent = mensagem;
  };

  const buscar = async () => {
    const minha = ++sequencia;
    const termo = entrada.value.trim();
    try {
      const resp = await fetch(`/api/v1/municipios?uf=${encodeURIComponent(uf)}&q=${encodeURIComponent(termo)}`);
      const corpo = await resp.json();
      if (minha !== sequencia) return;
      if (!resp.ok) return mostrar([], corpo.erro || "Busca indisponível no momento.");
      const n = corpo.resultados.length;
      mostrar(corpo.resultados, n ? `${n} município(s) encontrado(s).` : termo ? "Nenhum município encontrado." : "");
    } catch (e) {
      if (minha === sequencia) mostrar([], "Busca indisponível no momento.");
    }
  };

  entrada.addEventListener("input", () => {
    clearTimeout(temporizador);
    temporizador = setTimeout(buscar, 180);
  });
  entrada.addEventListener("focus", () => {
    if (!lista.children.length) buscar(); // sem digitar nada, sugere a capital
  });
}
