// Cargos proporcionais (Deputado Federal, Estadual e Distrital): composição em hemiciclo, bancadas por partido ou
// federação, candidatos mais votados (ou eleitos) com busca, e o painel completo de uma UF.
//
// O TSE publica, a cada totalização, quantas vagas cada partido/federação tem pelos votos apurados até aquele momento:
// enquanto a totalização final não chega, essa distribuição é provisória e o painel diz isso. "Eleito" só aparece
// quando o próprio TSE marca o candidato; o painel nunca decide quem se elegeu.
import { Atualizador } from "./net.js";
import { h, icone, limpar, quebravel } from "./dom.js";
import { Avisos, Heroi, Kpis, avisosDoResultado, celulaCandidato } from "./componentes.js";
import { Hemiciclo } from "./hemiciclo.js";
import * as dica from "./dica.js";
import * as fmt from "./fmt.js";

let contador = 0;
const novoId = (prefixo) => `${prefixo}-${++contador}`;

export const vagasTexto = fmt.vagas;

/** Mais vagas primeiro; empate (inclusive "nenhuma ainda"): mais votos; por fim, ordem alfabética. */
export const ordemBancada = (a, b) =>
  b.vagas - a.vagas || (b.votos_total ?? b.votos ?? 0) - (a.votos_total ?? a.votos ?? 0) || a.rotulo.localeCompare(b.rotulo, "pt-BR");

/** Texto da manchete e da linha de apoio de um cargo proporcional, a partir das bancadas (já ordenadas). Nunca inventa número. */
export function manchetePropor({ cargo, total, grupos, divulga, iniciou, final, textoFinal = "Totalização final concluída." }) {
  if (!divulga) {
    return { titulo: "Votos ainda não liberados", sub: "O TSE ainda não liberou os votos desta disputa. Seções e eleitorado já aparecem." };
  }
  if (!iniciou) {
    return {
      titulo: "A apuração ainda não começou",
      sub: `As ${fmt.inteiro(total)} vagas de ${cargo.toLowerCase()} aparecem distribuídas aqui assim que as primeiras urnas forem totalizadas.`,
    };
  }
  const [a, b] = grupos.filter((g) => g.vagas > 0);
  if (!a) return { titulo: "Apuração em andamento", sub: "O TSE ainda não distribuiu as vagas entre os partidos e federações." };
  const aviso = final ? textoFinal : "Distribuição provisória, pelos votos apurados até agora: muda até a totalização final.";
  if (b && b.vagas === a.vagas) {
    return { titulo: `${a.rotulo} e ${b.rotulo} empatam na maior bancada`, sub: `${vagasTexto(a.vagas)} cada, de ${fmt.inteiro(total)}. ${aviso}` };
  }
  const seguinte = b ? ` Em seguida, ${b.rotulo}, com ${fmt.inteiro(b.vagas)}.` : "";
  return { titulo: `${a.rotulo} tem a maior bancada`, sub: `${fmt.inteiro(a.vagas)} das ${fmt.inteiro(total)} vagas.${seguinte} ${aviso}` };
}

/** Dica de uma bancada: serve tanto aos grupos de uma UF (`votos_total`) quanto aos da soma nacional (`votos`, `ufs`). */
export function dicaDeBancada(g) {
  const corpo = h("div", {}, dica.titulo(g.rotulo));
  corpo.append(dica.linha(g.cor, vagasTexto(g.vagas), g.tipo === "f" ? "federação" : "partido"));
  const votos = g.votos_total ?? g.votos ?? 0;
  if (votos > 0) {
    const extra = g.pct_validos !== null && g.pct_validos !== undefined ? `${fmt.pct2(g.pct_validos)} dos válidos` : "";
    corpo.append(dica.linha(g.cor, fmt.inteiro(votos), "votos", extra));
  }
  if (g.ufs !== undefined && g.vagas > 0) corpo.append(dica.linha(g.cor, String(g.ufs), g.ufs === 1 ? "UF com vaga" : "UFs com vaga"));
  return corpo;
}

// ---- composição: hemiciclo + legenda + nota ------------------------------------------------------------------
export class Composicao {
  constructor({ unidade = "vagas" } = {}) {
    this.hemiciclo = new Hemiciclo({ unidade, dicaDe: (g) => dicaDeBancada(g.dados) });
    this.leg = h("ul", { class: "faixa-leg faixa-leg--bancadas", "aria-label": "Bancadas, com o número de vagas de cada uma" });
    this.nota = h("p", { class: "legenda-meta" });
    this.el = h("div", { class: "composicao" }, this.hemiciclo.el, this.leg, this.nota);
  }

  /** `grupos`: bancadas já ordenadas, no formato da API (`rotulo`, `cor`, `vagas`...). */
  atualizar({ total, grupos, nota }) {
    const comVagas = grupos.filter((g) => g.vagas > 0);
    this.hemiciclo.atualizar({
      total,
      grupos: comVagas.map((g) => ({ id: g.id ?? g.chave, rotulo: g.rotulo, cor: g.cor, vagas: g.vagas, dados: g })),
    });
    limpar(this.leg);
    comVagas.forEach((g, indice) => {
      const item = h("li", {}, h("span", { class: "chave", "data-cor": g.cor }), h("span", {}, quebravel(g.rotulo)), h("b", { texto: fmt.inteiro(g.vagas) }));
      // passar o mouse na legenda destaca os assentos da bancada (a tabela e a legenda dizem o mesmo para quem não usa mouse)
      item.addEventListener("pointerenter", (ev) => { if (ev.pointerType !== "touch") this.hemiciclo.destacar(indice); });
      item.addEventListener("pointerleave", () => this.hemiciclo.destacar(-1));
      this.leg.append(item);
    });
    this.leg.hidden = !comVagas.length;
    this.nota.textContent = nota || "";
    this.nota.hidden = !nota;
  }
}

// ---- tabelas -----------------------------------------------------------------------------------------------------
const celulaBancada = (g) => h("td", { title: g.tipo === "f" && g.nome ? fmt.nome(g.nome) : null },
  h("span", { class: "agr" }, h("span", { class: "chave", "data-cor": g.cor }), h("span", { class: "agr-nome" }, quebravel(g.rotulo)),
    g.tipo === "f" ? h("span", { class: "etiqueta", texto: "federação" }) : null));

const semValor = () => h("span", { class: "sem-valor", texto: "—" });

export class TabelaBancadas {
  /** `nacional`: as bancadas somadas de todas as UFs (outras colunas); senão, as de uma UF. */
  constructor({ nacional = false } = {}) {
    this.nacional = nacional;
    const th = (rotulo, classe, ajuda) => h("th", { scope: "col", class: classe || null, title: ajuda || null, texto: rotulo });
    const colunas = nacional
      ? [th("Partido ou federação"), th("Vagas", "num", "Vagas conforme o TSE publica durante a apuração; provisórias até a totalização final"),
        th("% das vagas", "num esconde-movel", "Parcela das vagas do cargo; calculada pelo painel"), th("Votos", "num"),
        th("UFs com vaga", "num esconde-movel", "Em quantas UFs o partido ou federação já tem pelo menos uma vaga")]
      : [th("Partido ou federação"), th("Vagas", "num", "Vagas conforme o TSE publica durante a apuração; provisórias até a totalização final"),
        th("Votos", "num esconde-movel", "Votos nominais e de legenda, como publicados pelo TSE"),
        th("% dos válidos", "num", "Votos do partido ou federação sobre os votos válidos da UF; calculado pelo painel"),
        th("Mais votado", "esconde-movel")];
    this.corpo = h("tbody");
    this.el = h("table", { class: "tabela tabela--bancadas" }, h("thead", {}, h("tr", {}, ...colunas)), this.corpo);
  }

  /** `grupos`: bancadas; `total`: vagas do cargo (só na visão nacional, para o % das vagas); `iniciou`: já há votos apurados. */
  atualizar(grupos, { total = 0, iniciou = true } = {}) {
    const ordenados = [...grupos].sort(ordemBancada);
    const maiorPct = Math.max(1, ...ordenados.map((g) => g.pct_validos || 0));
    limpar(this.corpo);
    for (const g of ordenados) {
      const nenhuma = g.vagas === 0;
      const votos = g.votos_total ?? g.votos ?? 0;
      const vagas = h("td", { class: "num" }, iniciou ? h("strong", { class: "vagas-n", texto: fmt.inteiro(g.vagas) }) : semValor());
      const nVotos = h("td", { class: this.nacional ? "num" : "num esconde-movel" }, votos > 0 ? fmt.inteiro(votos) : semValor());
      let celulas;
      if (this.nacional) {
        celulas = [celulaBancada(g), vagas,
          h("td", { class: "num esconde-movel" }, total > 0 && g.vagas > 0 ? fmt.pct2((100 * g.vagas) / total) : semValor()),
          nVotos, h("td", { class: "num esconde-movel" }, g.vagas > 0 ? String(g.ufs) : semValor())];
      } else {
        const medidor = h("span", { class: "mini-medidor", "aria-hidden": "true", "data-cor": g.cor }, h("span"));
        medidor.firstChild.style.width = `${Math.min(100, ((g.pct_validos || 0) / maiorPct) * 100)}%`;
        const mais = g.mais_votado;
        celulas = [celulaBancada(g), vagas, nVotos,
          h("td", { class: "num" }, g.pct_validos !== null && g.pct_validos !== undefined
            ? h("span", { class: "pct-celula" }, medidor, h("span", { texto: fmt.pct2(g.pct_validos) })) : semValor()),
          h("td", { class: "esconde-movel" }, mais
            ? h("span", { class: "nome-cor" }, h("span", { class: "sigla", "data-cor": g.cor, texto: mais.partido }), fmt.nome(mais.urna), " ",
              h("span", { class: "pct", texto: fmt.inteiro(mais.votos) }))
            : semValor())];
      }
      this.corpo.append(h("tr", { "data-sem-vaga": nenhuma ? "" : null }, ...celulas));
    }
  }
}

const COLUNAS_UF = {
  nome: (l) => l.nome,
  totalizado: (l) => (l.disponivel && l.secoes.pst ? l.secoes.pst.n : -1),
  vagas: (l) => (l.disponivel ? l.vagas : -1),
};

/** Uma linha por UF: andamento, vagas, os três agrupamentos mais votados e o candidato mais votado. */
export class TabelaUfsProporcional {
  constructor() {
    this.ordem = { chave: "nome", dir: 1 };
    this.linhas = [];
    this.cabecalho = h("tr");
    this.corpo = h("tbody");
    this.el = h("table", { class: "tabela tabela--ufs" }, h("thead", {}, this.cabecalho), this.corpo);
    this.montarCabecalho();
  }

  /** `curto`: forma abreviada do título, usada no celular (a tabela não tem largura para o nome inteiro). */
  th(rotulo, chave, classe, ajuda, curto = null) {
    const ativa = chave && this.ordem.chave === chave;
    const texto = curto ? [h("span", { class: "rot-longo", texto: rotulo }), h("span", { class: "rot-curto", texto: curto })] : rotulo;
    const conteudo = chave
      ? h("button", { class: "th-botao", type: "button", onclick: () => this.ordenarPor(chave) }, texto, ativa ? (this.ordem.dir > 0 ? " ▲" : " ▼") : "")
      : texto;
    return h("th", { class: classe || null, title: ajuda || null, scope: "col", "aria-sort": ativa ? (this.ordem.dir > 0 ? "ascending" : "descending") : null }, conteudo);
  }

  montarCabecalho() {
    limpar(this.cabecalho).append(
      this.th("UF", "nome"),
      this.th("Totalizado", "totalizado", null, "Percentual das seções totalizadas", "Apurado"),
      this.th("Vagas", "vagas", "num", "Vagas do cargo na UF"),
      this.th("1º mais votado", null, null, "Partido ou federação com mais votos, e o percentual dos votos válidos (calculado pelo painel)"),
      this.th("2º", null, "esconde-pequeno"),
      this.th("3º", null, "esconde-medio"),
      this.th("Candidato mais votado", null, "esconde-medio"),
    );
  }

  ordenarPor(chave) {
    this.ordem = { chave, dir: this.ordem.chave === chave ? -this.ordem.dir : chave === "nome" ? 1 : -1 };
    this.montarCabecalho();
    this.pintar();
  }

  atualizar(linhas) {
    this.linhas = linhas;
    this.pintar();
  }

  pintar() {
    const valor = COLUNAS_UF[this.ordem.chave];
    const ordenadas = [...this.linhas].sort((a, b) => {
      const va = valor(a), vb = valor(b);
      const cmp = typeof va === "string" ? va.localeCompare(vb, "pt-BR") : va - vb;
      return cmp * this.ordem.dir || a.nome.localeCompare(b.nome, "pt-BR");
    });
    limpar(this.corpo);
    for (const l of ordenadas) {
      // no celular a UF vira a sigla (SP, MG...): sobra largura para o nome dos partidos; o leitor de tela continua ouvindo o nome inteiro
      const nome = h("a", { class: "linha-link", href: `/uf/${l.codigo}${window.location.search}#${l.cargo}`, "aria-label": l.nome },
        h("span", { class: "uf-nome", texto: l.nome }), h("span", { class: "uf-sigla", "aria-hidden": "true", texto: l.codigo.toUpperCase() }));
      const etiqueta = l.cargo === "deputado-distrital" ? h("span", { class: "etiqueta", texto: "distrital" }) : null;
      const primeira = h("td", {}, h("span", { class: "agr" }, nome, etiqueta));
      if (!l.disponivel) {
        this.corpo.append(h("tr", {}, primeira, h("td", { colspan: "6" }, h("span", { class: "sem-valor", texto: "Aguardando dados do TSE" }))));
        continue;
      }
      const medidor = h("span", { class: "mini-medidor", "aria-hidden": "true" }, h("span"));
      medidor.firstChild.style.width = `${Math.min(100, l.secoes.pst ? l.secoes.pst.n : 0)}%`;
      const mais = l.mais_votado;
      this.corpo.append(h("tr", {}, primeira,
        h("td", {}, medidor, fmt.pct(l.secoes.pst)),
        h("td", { class: "num" }, h("strong", { class: "vagas-n", texto: fmt.inteiro(l.vagas) })),
        celulaCandidato(l.top[0], false),
        Object.assign(celulaCandidato(l.top[1], false), { className: "esconde-pequeno" }),
        Object.assign(celulaCandidato(l.top[2], false), { className: "esconde-medio" }),
        h("td", { class: "esconde-medio", title: mais ? `${fmt.nome(mais.urna)} · ${fmt.inteiro(mais.votos)} votos` : null }, mais
          ? h("span", { class: "nome-cor" }, h("span", { class: "sigla", "data-cor": mais.cor, texto: mais.partido }), fmt.nome(mais.urna))
          : semValor())));
    }
  }
}

// ---- candidatos -----------------------------------------------------------------------------------------------------
/** Lista de candidatos em ordem de votos. As barras comparam cada um com o mais votado da UF (escala relativa, dita na nota). */
export class ListaCandidatos {
  constructor() {
    this.linhas = new Map();
    this.el = h("ol", { class: "ranking ranking--dep" });
  }

  criar(c) {
    const linha = { c };
    linha.pos = h("span", { class: "cand-pos", "aria-hidden": "true" });
    linha.foto = h("img", { class: "foto", alt: "", width: "44", height: "56", loading: "lazy", decoding: "async" });
    linha.nome = h("span", { class: "cand-nome" });
    linha.sigla = h("span", { class: "sigla" });
    linha.numero = h("span", { class: "numero" });
    linha.selo = h("span", { class: "selo", hidden: true });
    linha.preench = h("span", { class: "barra-preench" });
    linha.extra = h("div", { class: "cand-extra" });
    linha.pct = h("strong", { class: "cand-pct" });
    linha.votos = h("span", { class: "cand-votos" });
    linha.el = h("li", { class: "cand", tabindex: "0" },
      linha.pos, linha.foto,
      h("div", {}, h("div", { class: "cand-topo" }, linha.nome, h("span", { class: "cand-partido" }, linha.sigla, linha.numero), linha.selo),
        h("div", { class: "barra", "aria-hidden": "true" }, h("span", { class: "barra-trilho" }), linha.preench), linha.extra),
      h("div", { class: "cand-nums" }, linha.pct, linha.votos));
    dica.vincular(linha.el, () => h("div", {}, dica.titulo(`${linha.c.urna} · ${linha.c.partido} ${linha.c.numero}`),
      dica.linha(linha.c.cor, fmt.pct(linha.c.pct), "dos votos"), dica.linha(linha.c.cor, fmt.inteiro(linha.c.votos), "votos"),
      h("div", { class: "dica-linha" }, h("span", { texto: linha.c.nome }))));
    return linha;
  }

  preencher(linha, c, maximo) {
    linha.c = c;
    const foto = c.foto;
    if (linha.foto.getAttribute("src") !== foto) linha.foto.src = foto;
    linha.pos.textContent = String(c.posicao);
    linha.nome.textContent = c.urna;
    linha.sigla.textContent = c.partido;
    linha.sigla.dataset.cor = c.cor;
    linha.numero.textContent = c.numero;
    linha.pct.textContent = c.votos > 0 ? fmt.pct(c.pct) : "—";
    linha.votos.textContent = c.votos > 0 ? `${fmt.inteiro(c.votos)} votos` : "";
    linha.preench.dataset.cor = c.cor;
    linha.preench.style.width = `${c.votos > 0 ? Math.max(1.5, Math.min(100, (100 * c.votos) / maximo)) : 0}%`;
    if (c.eleito) {
      limpar(linha.selo).append(icone("ok"), c.situacao || "Eleito");
      linha.selo.hidden = false;
    } else {
      linha.selo.hidden = true;
    }
    // voto anulado (ex.: candidatura indeferida) não conta para o partido; o TSE diz "Anulado" ou "Anulado sub judice"
    const anulado = /^anulad/i.test(c.destino || "");
    const aviso = anulado ? `Votos ${c.destino.toLowerCase().replace(/^anulado/, "anulados")}` : "";
    linha.el.toggleAttribute("data-anulado", anulado);
    linha.extra.textContent = [aviso, !c.eleito ? c.situacao : ""].filter(Boolean).join(" · ");  // ex.: "Suplente", como o TSE publica
    linha.el.setAttribute("aria-label", `${c.posicao}º, ${c.urna}, ${c.partido}${c.eleito ? `, ${c.situacao || "eleito"}` : ""}, ${c.votos > 0 ? `${fmt.inteiro(c.votos)} votos` : "sem votos apurados"}${aviso ? `, ${aviso.toLowerCase()}` : ""}`);
  }

  atualizar(itens, maximo = 1) {
    this.el.style.setProperty("--linhas", String(Math.ceil(itens.length / 2)));
    const vistos = new Set();
    const desejada = itens.map((c) => {
      vistos.add(c.sq);
      let linha = this.linhas.get(c.sq);
      if (!linha) {
        linha = this.criar(c);
        this.linhas.set(c.sq, linha);
      }
      this.preencher(linha, c, Math.max(1, maximo));
      return linha.el;
    });
    for (const [sq, linha] of this.linhas) {
      if (!vistos.has(sq)) {
        linha.el.remove();
        this.linhas.delete(sq);
      }
    }
    desejada.forEach((el, i) => {
      if (this.el.children[i] !== el) this.el.insertBefore(el, this.el.children[i] || null);
    });
  }
}

const POR_PAGINA = 20; // igual ao da API (`tamanho`) e ao número de "mais votados" que vem no painel

/**
 * Seção "candidatos" de uma UF: por padrão, os eleitos (quando o TSE já marcou) ou os mais votados até agora;
 * ao buscar por nome/número ou escolher um partido, o resultado da busca, 20 por vez.
 */
export class SecaoCandidatos {
  constructor({ slug, uf, turno }) {
    this.url = `/api/v1/proporcional/${slug}/${uf}/candidatos`;
    this.turno = turno;
    this.dados = null;
    this.paginas = 1;
    this.versao = 0;
    this.espera = null;
    this.idsFiltro = "";
    const id = novoId("cand");
    this.titulo = h("h2", { class: "sec-tit", id, texto: "Candidatos mais votados" });
    this.sub = h("p", { class: "sub", "aria-live": "polite" });
    this.campo = h("input", {
      class: "campo", type: "search", autocomplete: "off", placeholder: "Nome ou número do candidato…",
      "aria-label": "Buscar candidato por nome ou número", maxlength: "60",
    });
    this.filtro = h("select", { class: "seletor", "aria-label": "Filtrar por partido ou federação" });
    this.limparBusca = h("button", { class: "btn-texto", type: "button", hidden: true, texto: "Limpar busca", onclick: () => this.limpar() });
    this.lista = new ListaCandidatos();
    this.aviso = h("p", { class: "vazio", hidden: true });
    this.mais = h("button", { class: "btn-texto", type: "button", hidden: true, texto: "Mostrar mais", onclick: () => this.maisUma() });
    this.nota = h("p", { class: "legenda-meta", texto: "As barras comparam cada candidato com o mais votado da UF. Votos e percentuais como publicados pelo TSE." });
    this.campo.addEventListener("input", () => {
      clearTimeout(this.espera);
      this.espera = setTimeout(() => this.mudou(), 250);
    });
    this.campo.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && this.campo.value) this.limpar();
    });
    this.filtro.addEventListener("change", () => this.mudou());
    this.el = h("section", { class: "sec", "aria-labelledby": id },
      h("header", { class: "sec-cab" }, this.titulo, this.sub),
      h("div", { class: "ferramentas" }, this.campo, this.filtro, this.limparBusca),
      this.lista.el, this.aviso, h("div", { class: "mais-linha" }, this.mais), this.nota);
  }

  get buscando() {
    return this.campo.value.trim() !== "" || this.filtro.value !== "";
  }

  limpar() {
    this.campo.value = "";
    this.filtro.value = "";
    this.mudou();
  }

  mudou() {
    this.paginas = 1;
    this.recarregar();
  }

  maisUma() {
    this.paginas += 1;
    this.recarregar();
  }

  montarFiltro(grupos) {
    const ordenados = [...grupos].sort(ordemBancada);
    const ids = ordenados.map((g) => g.id).join(",");
    if (ids === this.idsFiltro) return;
    this.idsFiltro = ids;
    const atual = this.filtro.value;
    limpar(this.filtro).append(h("option", { value: "", texto: "Todos os partidos e federações" }),
      ...ordenados.map((g) => h("option", { value: g.id, texto: g.tipo === "f" ? `${g.rotulo} (federação)` : g.rotulo })));
    this.filtro.value = ordenados.some((g) => g.id === atual) ? atual : "";
  }

  /** Painel com dado novo: atualiza o filtro e refaz a lista (incluindo as páginas já abertas). */
  atualizar(d) {
    this.dados = d;
    this.montarFiltro(d.agrupamentos);
    this.recarregar();
  }

  async buscarPaginas(de, ate) {
    const q = this.campo.value.trim();
    const paginas = await Promise.all(Array.from({ length: ate - de + 1 }, async (_, i) => {
      const params = new URLSearchParams({ q, agr: this.filtro.value, pagina: String(de + i) });
      if (this.turno) params.set("turno", this.turno);
      const resp = await fetch(`${this.url}?${params}`, { headers: { Accept: "application/json" } });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return resp.json();
    }));
    return { itens: paginas.flatMap((p) => p.itens), total: paginas.at(-1).total, totalPaginas: paginas.at(-1).paginas };
  }

  async recarregar() {
    const d = this.dados;
    if (!d) return;
    const versao = ++this.versao;
    const maximo = (d.destaques[0] && d.destaques[0].votos) || 1;
    try {
      let itens, total, totalPaginas, titulo, sub;
      if (this.buscando) {
        ({ itens, total, totalPaginas } = await this.buscarPaginas(1, this.paginas));
        titulo = "Resultado da busca";
        sub = total === 1 ? "1 candidato encontrado" : `${fmt.inteiro(total)} candidatos encontrados`;
      } else if (d.eleitos.length) {
        itens = d.eleitos;
        total = itens.length;
        totalPaginas = 1;
        titulo = "Eleitos";
        sub = `${fmt.inteiro(total)} marcados como eleitos pelo TSE, na ordem de votos.`;
      } else {
        const extras = this.paginas > 1 ? await this.buscarPaginas(2, this.paginas) : { itens: [] };
        itens = [...d.destaques, ...extras.itens];
        total = d.total_candidatos;
        // enquanto menos de uma página de candidatos tem votos, o resto da fila é só ordem de registro: a busca encontra quem for
        totalPaginas = d.destaques.length < POR_PAGINA ? 1 : Math.max(1, Math.ceil(total / POR_PAGINA));
        titulo = "Candidatos mais votados";
        sub = itens.length
          ? "Em ordem de votos, até agora. O TSE só marca os eleitos na totalização final."
          : "Os candidatos aparecem aqui, em ordem de votos, assim que a apuração começar.";
      }
      if (versao !== this.versao) return; // chegou uma busca mais nova
      if (this.titulo.textContent !== titulo) this.titulo.textContent = titulo;
      if (this.sub.textContent !== sub) this.sub.textContent = sub;
      this.lista.atualizar(itens, maximo);
      this.lista.el.hidden = !itens.length;
      this.aviso.hidden = itens.length > 0 || !this.buscando;
      this.aviso.textContent = "Nenhum candidato encontrado. Confira o nome ou o número, ou escolha outro partido.";
      this.mais.hidden = this.paginas >= totalPaginas || (!this.buscando && d.eleitos.length > 0);
      this.limparBusca.hidden = !this.buscando;
    } catch {
      if (versao === this.versao) {
        this.aviso.hidden = false;
        this.aviso.textContent = "Não foi possível consultar os candidatos agora. Tente de novo em instantes.";
      }
    }
  }
}

// ---- painel completo de uma UF ---------------------------------------------------------------------------------------
const secao = (titulo, ...conteudo) => {
  const id = novoId("sec");
  return h("section", { class: "sec", "aria-labelledby": id },
    h("header", { class: "sec-cab" }, h("h2", { class: "sec-tit", id, texto: titulo })), ...conteudo);
};

export class PainelProporcional {
  /** `aoFrescor`/`aoErro`: repassam à "casca" da página o estado da conexão; `aoFase`: fase (oficial/simulado) dos arquivos. */
  constructor({ slug, nome, uf, nomeUf, turno = null, aoFrescor, aoErro, aoFase }) {
    this.slug = slug;
    this.nome = nome;
    this.aoFase = aoFase;
    this.avisos = new Avisos(h("div", { class: "avisos", "aria-live": "polite" }));
    this.kicker = h("p", { class: "kicker", texto: `${nome} · ${nomeUf}` });
    this.titulo = h("h2", { class: "manchete", texto: "Carregando a apuração…" });
    this.sub = h("p", { class: "manchete-sub", hidden: true });
    this.heroi = new Heroi({ rotulo: "Seções totalizadas" });
    this.composicao = new Composicao();
    this.tabela = new TabelaBancadas();
    this.candidatos = new SecaoCandidatos({ slug, uf, turno });
    this.kpis = new Kpis({ faixa: true });
    this.el = h("section", { id: `painel-${slug}`, role: "tabpanel", class: "grade-pagina painel-disputa", hidden: true },
      this.avisos.raiz,
      h("div", { class: "abertura abertura--uf abertura--cargo" },
        h("div", { class: "abertura-esq" }, h("div", { class: "placar" }, this.kicker, this.titulo, this.sub), this.heroi.el),
        secao("Composição", h("div", { class: "cartao cartao-hemiciclo" }, this.composicao.el))),
      secao(`Bancadas em ${nomeUf}`, h("div", { class: "cartao" }, h("div", { class: "rolagem" }, this.tabela.el))),
      this.candidatos.el,
      secao("Eleitorado", this.kpis.el));
    this.atualizador = new Atualizador({
      url: `/api/v1/proporcional/${slug}/${uf}${turno ? `?turno=${encodeURIComponent(turno)}` : ""}`,
      aoDados: (d) => this.atualizar(d), aoFrescor, aoErro,
      aoIndisponivel: (msg) => this.avisos.atualizar([{ tipo: "info", titulo: "Sem dados deste cargo agora.", texto: msg }]),
    });
    this.atualizador.pausado = true;
    this.ativo = false;
    this.iniciado = false;
  }

  /** Só consulta a API enquanto a aba está à vista. */
  definirAtivo(ativo) {
    if (ativo === this.ativo) return;
    this.ativo = ativo;
    this.atualizador.pausado = !ativo;
    if (!ativo) return;
    if (this.iniciado) this.atualizador.buscar();
    else {
      this.iniciado = true;
      this.atualizador.iniciar();
    }
  }

  atualizar(d) {
    if (!d.disponivel) {
      this.avisos.atualizar([{ tipo: "info", titulo: "Aguardando dados do TSE.", texto: "A consulta a este local começou agora." }]);
      return;
    }
    const r = d.resultado;
    this.aoFase?.(r.fase);
    this.avisos.atualizar(avisosDoResultado(r));
    const total = r.cargo.vagas;
    const grupos = [...d.agrupamentos].sort(ordemBancada);
    const iniciou = r.estado.divulga && r.secoes.st > 0 && grupos.some((g) => g.votos_total > 0);
    const final = r.estado.totalizacao_final;
    const { titulo, sub } = manchetePropor({ cargo: r.cargo.nome, total, grupos, divulga: r.estado.divulga, iniciou, final });
    this.titulo.textContent = titulo;
    this.sub.textContent = sub;
    this.sub.hidden = !sub;

    let nota;
    if (final) nota = "Totalização final concluída: as vagas são as definitivas.";
    else if (iniciou) {
      const qe = r.cargo.quociente_eleitoral;
      nota = `Vagas conforme o TSE publica durante a apuração, com os votos apurados até agora${qe ? ` (quociente eleitoral provisório: ${fmt.inteiro(qe)} votos)` : ""}. Mudam até a totalização final.`;
    } else nota = "As vagas são distribuídas entre os partidos e federações em proporção aos votos de cada um e aparecem aqui assim que a apuração começar.";
    this.composicao.atualizar({ total, grupos, nota });
    this.tabela.atualizar(grupos, { iniciou });
    this.candidatos.atualizar(d);
    this.heroi.atualizar(r);
    this.kpis.atualizar(r);
  }
}
