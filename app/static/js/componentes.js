// Componentes de interface. Cada um cria seu nó uma vez (`el`) e se atualiza com `atualizar(...)`,
// reaproveitando os elementos para as barras e os blocos animarem em vez de piscar.
import { definirTexto, h, icone, limpar, piscar, quebravel } from "./dom.js";
import * as fmt from "./fmt.js";
import * as dica from "./dica.js";

let contador = 0;
const novoId = (prefixo) => `${prefixo}-${++contador}`;

// ---- avisos ---------------------------------------------------------------------------------------
const ICONE_AVISO = { ok: "ok", info: "info", atencao: "alerta", critico: "erro" };

export class Avisos {
  constructor(raiz) {
    this.raiz = raiz;
    this.chave = null;
  }

  atualizar(lista) {
    const chave = JSON.stringify(lista);
    if (chave === this.chave) return;
    this.chave = chave;
    limpar(this.raiz);
    for (const a of lista) {
      this.raiz.append(
        h("div", { class: "aviso", "data-tipo": a.tipo }, icone(ICONE_AVISO[a.tipo] || "info"),
          h("div", {}, h("strong", { texto: a.titulo }), a.texto ? h("span", { texto: ` ${a.texto}` }) : null)),
      );
    }
  }
}

// Avisos que decorrem do estado de um resultado. O que a manchete do placar já diz (votos não liberados,
// apuração não iniciada, quem lidera, segundo turno) não se repete aqui.
export function avisosDoResultado(r) {
  const lista = [];
  const e = r.estado;
  if (e.totalizacao_final) lista.push({ tipo: "ok", titulo: "Totalização final concluída." });
  if (e.sem_eleito) lista.push({ tipo: "atencao", titulo: "Sem atribuição de eleito.", texto: (e.motivos || []).join(" ") });
  return lista;
}

// ---- andamento: progresso da totalização -----------------------------------------------------------------
export class Heroi {
  constructor({ rotulo = "Seções totalizadas" } = {}) {
    const id = novoId("heroi");
    this.num = h("p", { class: "heroi-num" });
    this.preench = h("span");
    this.medidor = h("div", { class: "medidor", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100" }, this.preench);
    this.sub = h("p", { class: "sub" });
    this.el = h("section", { class: "heroi", "aria-labelledby": id },
      h("p", { class: "rotulo", id, texto: rotulo }), this.num, this.medidor, this.sub);
  }

  atualizar(r) {
    const s = r.secoes;
    const texto = s.pst ? s.pst.t : "0,00";
    const n = s.pst ? s.pst.n : 0;
    if (this.ultimo !== undefined && this.ultimo !== texto) piscar(this.num);
    this.ultimo = texto;
    limpar(this.num).append(texto, h("small", { texto: "%" }));
    this.preench.style.width = `${Math.min(100, Math.max(0, n))}%`;
    this.medidor.setAttribute("aria-valuenow", String(Math.round(n)));
    this.medidor.setAttribute("aria-label", `${texto}% das seções totalizadas`);
    const partes = [`${fmt.inteiro(s.st)} de ${fmt.inteiro(s.ts)} seções`];
    partes.push(r.totalizado_em ? `última totalização às ${fmt.hora(r.totalizado_em)} (horário de Brasília)` : "apuração ainda não iniciada");
    this.sub.textContent = partes.join(" · ");
  }
}

// ---- indicadores -------------------------------------------------------------------------------------------
const KPIS = [
  ["eleitorado", "Eleitorado", "Eleitores aptos a votar na abrangência"],
  ["comparecimento", "Comparecimento", "Percentual sobre os eleitores das seções instaladas"],
  ["abstencao", "Abstenção", "Percentual sobre os eleitores das seções instaladas"],
  ["brancos", "Votos em branco", "Percentual sobre o total de votos"],
  ["nulos", "Votos nulos", "Percentual sobre o total de votos"],
];

export class Kpis {
  /** `faixa`: os cinco indicadores lado a lado (em vez de uma lista vertical). */
  constructor({ faixa = false } = {}) {
    this.refs = {};
    this.el = h("div", { class: faixa ? "kpis kpis--faixa" : "kpis" });
    for (const [chave, rotulo, ajuda] of KPIS) {
      const valor = h("p", { class: "kpi-valor" });
      const sub = h("p", { class: "kpi-sub" });
      this.refs[chave] = { valor, sub };
      this.el.append(h("div", { class: "kpi", title: ajuda }, h("p", { class: "rotulo", texto: rotulo }), valor, sub));
    }
  }

  definir(chave, valor, sub) {
    definirTexto(this.refs[chave].valor, valor);
    this.refs[chave].sub.textContent = sub;
  }

  atualizar(r) {
    const { eleitorado: e, votos: v, secoes: s } = r;
    const iniciou = s.st > 0;
    const temVotos = r.estado.divulga && v.tv > 0;
    this.definir("eleitorado", fmt.compacto(e.te), `${fmt.inteiro(e.te)} eleitores aptos`);
    this.definir("comparecimento", iniciou ? fmt.pct(e.pc) : "—", iniciou ? `${fmt.inteiro(e.c)} eleitores` : "aguardando urnas");
    this.definir("abstencao", iniciou ? fmt.pct(e.pa) : "—", iniciou ? `${fmt.inteiro(e.a)} eleitores` : "aguardando urnas");
    this.definir("brancos", temVotos ? fmt.pct(v.pvb) : "—", temVotos ? `${fmt.inteiro(v.vb)} votos` : "aguardando votos");
    this.definir("nulos", temVotos ? fmt.pct(v.ptvn) : "—", temVotos ? `${fmt.inteiro(v.tvn)} votos` : "aguardando votos");
  }
}

// ---- ranking de candidatos ---------------------------------------------------------------------------
export class Ranking {
  /** `metaCinquenta`: desenha a linha de 50% (Presidente e Governador); `corte`: linha após as vagas (Senador). */
  constructor({ metaCinquenta = false, corte = false } = {}) {
    this.metaCinquenta = metaCinquenta;
    this.corte = corte;
    this.linhas = new Map();
    this.lista = h("ol", { class: "ranking" });
    this.marcaCorte = h("li", { class: "corte" }); // entra no DOM só quando há linha de corte
    const notas = [];
    if (metaCinquenta) notas.push("A linha marca 50%: no 1º turno, é eleito quem obtém mais da metade dos votos válidos (sem contar brancos e nulos).");
    notas.push("Percentuais e votos exatamente como publicados pelo TSE.");
    this.el = h("div", {}, this.lista, h("p", { class: "legenda-meta", texto: notas.join(" ") }));
  }

  criarLinha(c) {
    const linha = { c };
    linha.pos = h("span", { class: "cand-pos", "aria-hidden": "true" });
    linha.foto = h("img", { class: "foto", alt: "", width: "44", height: "56", loading: "lazy", decoding: "async", src: c.foto });
    linha.nome = h("span", { class: "cand-nome" });
    linha.sigla = h("span", { class: "sigla" });
    linha.numero = h("span", { class: "numero" });
    linha.selo = h("span", { class: "selo", hidden: true });
    linha.preench = h("span", { class: "barra-preench" });
    linha.extra = h("div", { class: "cand-extra" });
    linha.pct = h("strong", { class: "cand-pct" });
    linha.votos = h("span", { class: "cand-votos" });
    const barra = h("div", { class: "barra", "aria-hidden": "true" },
      h("span", { class: "barra-trilho" }), linha.preench, this.metaCinquenta ? h("span", { class: "barra-meta" }) : null);
    linha.el = h("li", { class: "cand", tabindex: "0" },
      linha.pos,
      linha.foto,
      h("div", {}, h("div", { class: "cand-topo" }, linha.nome, h("span", { class: "cand-partido" }, linha.sigla, linha.numero), linha.selo), barra, linha.extra),
      h("div", { class: "cand-nums" }, linha.pct, linha.votos));
    dica.vincular(linha.el, () => this.dicaDe(linha.c));
    return linha;
  }

  dicaDe(c) {
    return h("div", {}, dica.titulo(`${c.urna} · ${c.partido} ${c.numero}`),
      dica.linha(c.cor, fmt.pct(c.pct), "dos votos"), dica.linha(c.cor, fmt.inteiro(c.votos), "votos"),
      h("div", { class: "dica-linha" }, h("span", { texto: c.nome })));
  }

  preencher(linha, c, posicao, iniciou, r) {
    linha.c = c;
    if (linha.foto.getAttribute("src") !== c.foto) linha.foto.src = c.foto;
    linha.pos.textContent = String(posicao + 1);
    linha.nome.textContent = c.urna;
    linha.sigla.textContent = c.partido;
    linha.numero.textContent = c.numero;
    linha.sigla.dataset.cor = c.cor;
    definirTexto(linha.pct, iniciou ? fmt.pct(c.pct) : "—");
    definirTexto(linha.votos, iniciou ? `${fmt.inteiro(c.votos)} votos` : "");
    linha.preench.dataset.cor = c.cor;
    linha.preench.style.width = iniciou ? `${Math.min(100, Math.max(0, c.pct.n))}%` : "0%";

    if (c.eleito) {
      const rotulo = c.situacao || (r.estado.definido === "s" ? "2º turno" : "Eleito");
      limpar(linha.selo).append(icone(/^Eleit/.test(rotulo) ? "ok" : "info"), rotulo);
      linha.selo.hidden = false;
    } else {
      linha.selo.hidden = true;
    }

    if (c.vice) linha.extra.textContent = `Vice: ${c.vice}`;
    else if (c.suplentes && c.suplentes.length) linha.extra.textContent = `Suplentes: ${c.suplentes.join(", ")}`;
    else linha.extra.textContent = "";
    linha.el.setAttribute("aria-label", `${c.urna}, ${c.partido}, ${iniciou ? `${fmt.pct(c.pct)} dos votos, ${fmt.inteiro(c.votos)} votos` : "sem votos apurados"}`);
  }

  atualizar(r) {
    const iniciou = r.secoes.st > 0 && r.estado.divulga;
    const vagas = (r.cargo && r.cargo.vagas) || 1;
    const usarCorte = this.corte && r.candidatos.length > vagas;
    const vistos = new Set();
    const desejada = [];
    r.candidatos.forEach((c, i) => {
      vistos.add(c.sq);
      let linha = this.linhas.get(c.sq);
      if (!linha) {
        linha = this.criarLinha(c);
        this.linhas.set(c.sq, linha);
      }
      this.preencher(linha, c, i, iniciou, r);
      desejada.push(linha.el);
      if (usarCorte && i === vagas - 1) {
        this.marcaCorte.textContent = vagas === 1 ? "1 vaga" : `${vagas} vagas`;
        desejada.push(this.marcaCorte);
      }
    });
    if (!usarCorte) this.marcaCorte.remove();
    for (const [sq, linha] of this.linhas) {
      if (!vistos.has(sq)) {
        linha.el.remove();
        this.linhas.delete(sq);
      }
    }
    // só move o que está fora de lugar (mover um nó interrompe a animação da barra)
    desejada.forEach((el, i) => {
      if (this.lista.children[i] !== el) this.lista.insertBefore(el, this.lista.children[i] || null);
    });
  }
}

// ---- UF no mapa: quem lidera, dica e descrição acessível (compartilhados pelo mapa geográfico e pelo de blocos) ----
/** Cor de um candidato numa visão que cruza UFs: `porPartido` usa a cor do partido (igual em todas as UFs). */
export const corDe = (c, porPartido) => (porPartido && c.cor_partido) || c.cor;

/** Candidato à frente na UF, ou null se ainda não há votos liberados. */
export function liderDaUf(l) {
  return l && l.disponivel && l.top.length ? l.top[0] : null;
}

/** Dica (tooltip) de uma UF: totalização e os primeiros colocados. */
export function dicaDeUf(l, porPartido = false) {
  if (!l) return null;
  const corpo = h("div", {}, dica.titulo(l.nome));
  if (!l.disponivel) {
    corpo.append(h("div", { class: "dica-linha", texto: "Aguardando dados do TSE" }));
    return corpo;
  }
  corpo.append(h("div", { class: "dica-linha", texto: `${fmt.pct(l.secoes.pst)} das seções totalizadas` }));
  if (l.totalizado_em) corpo.append(h("div", { class: "dica-linha", texto: `Última totalização da UF às ${fmt.hora(l.totalizado_em)}` }));
  for (const c of l.top) {
    // nos deputados a linha é um partido ou federação: o que importa é o percentual dos votos válidos e as vagas
    if (c.bancada) corpo.append(dica.linha(c.cor, fmt.pct(c.pct), c.urna, fmt.vagas(c.vagas)));
    else corpo.append(dica.linha(corDe(c, porPartido), fmt.pct(c.pct), `${fmt.nome(c.urna)} · ${c.partido}`, `${fmt.inteiro(c.votos)} votos`));
  }
  if (!l.top.length) corpo.append(h("div", { class: "dica-linha", texto: l.divulga ? "Sem votos apurados" : "Votação ainda não liberada" }));
  else if (l.top[0].bancada) {
    corpo.append(h("div", { class: "dica-linha dica-nota", texto: `${fmt.vagas(l.vagas)} em disputa; % dos votos válidos calculado pelo painel` }));
    if (l.mais_votado) corpo.append(h("div", { class: "dica-linha dica-nota", texto: `Candidato mais votado: ${fmt.nome(l.mais_votado.urna)} (${l.mais_votado.partido}), ${fmt.inteiro(l.mais_votado.votos)} votos` }));
  }
  return corpo;
}

/** Texto lido por leitores de tela para uma UF (o nome é passado à parte porque o mapa já o conhece antes dos dados). */
export function descreverUf(nome, l) {
  const lider = liderDaUf(l);
  if (lider && lider.bancada) {
    return `${nome}: ${lider.urna} é o mais votado, com ${fmt.pct(lider.pct)} dos votos válidos e ${fmt.vagas(lider.vagas)} de ${l.vagas}; ${fmt.pct(l.secoes.pst)} das seções totalizadas`;
  }
  return lider
    ? `${nome}: ${lider.urna} (${lider.partido}) à frente com ${fmt.pct(lider.pct)}; ${fmt.pct(l.secoes.pst)} das seções totalizadas`
    : `${nome}: ${l && l.disponivel && l.secoes.st > 0 ? "sem votos liberados" : "apuração não iniciada"}`;
}

// ---- mapa em blocos ------------------------------------------------------------------------------------
export const ORDEM_BLOCOS = [
  "rr", "ap", "am", "pa", "ma", "ce", "rn", "ac", "ro", "mt", "to", "pi", "pe", "pb",
  "ms", "go", "ba", "al", "df", "mg", "se", "pr", "sp", "rj", "es", "sc", "rs", "zz",
];

export class Mapa {
  /** `quem`: como o texto se refere a quem pinta a UF (padrão: "do candidato que lidera"). */
  constructor({ porPartido = false, quem = "do candidato que lidera" } = {}) {
    this.porPartido = porPartido;
    this.dados = new Map();
    this.blocos = new Map();
    this.el = h("div", { class: "mapa", role: "group", "aria-label": `Mapa de blocos das UFs, colorido pela cor ${quem}` });
    for (const uf of ORDEM_BLOCOS) {
      const bloco = {};
      bloco.uf = h("b", { texto: uf === "zz" ? "EX" : uf.toUpperCase() });
      bloco.valor = h("span");
      bloco.prog = h("i");
      const filhos = [bloco.uf, bloco.valor, bloco.prog];
      bloco.el = uf === "zz"
        ? h("div", { class: `bloco uf-${uf}`, "data-uf": uf, tabindex: "0", role: "img" }, ...filhos)
        : h("a", { class: `bloco uf-${uf}`, "data-uf": uf, href: `/uf/${uf}${window.location.search}` }, ...filhos);
      dica.vincular(bloco.el, () => dicaDeUf(this.dados.get(uf), this.porPartido));
      this.blocos.set(uf, bloco);
      this.el.append(bloco.el);
    }
  }

  atualizar(ufs) {
    for (const l of ufs) {
      this.dados.set(l.codigo, l);
      const b = this.blocos.get(l.codigo);
      if (!b) continue;
      const lider = liderDaUf(l);
      if (l.cargo && b.el.tagName === "A") b.el.setAttribute("href", `/uf/${l.codigo}${window.location.search}#${l.cargo}`); // abre a aba do cargo
      if (lider) {
        b.el.dataset.cor = corDe(lider, this.porPartido);
        delete b.el.dataset.semDados;
        b.valor.textContent = fmt.pct(lider.pct);
      } else {
        delete b.el.dataset.cor;
        b.el.dataset.semDados = "";
        b.valor.textContent = l.disponivel && l.secoes.st > 0 ? "—" : "";
      }
      b.prog.style.width = l.disponivel && l.secoes.pst ? `${Math.min(100, l.secoes.pst.n)}%` : "0%";
      b.el.setAttribute("aria-label", descreverUf(l.nome, l));
    }
    // sem dados do exterior (Governador e Senador não têm): o bloco "EX" some
    const ex = this.blocos.get("zz");
    if (ex) ex.el.hidden = !this.dados.has("zz");
  }
}

/** Quantas UFs cada candidato (ou partido, nas disputas em que o candidato muda de UF para UF) lidera. */
export class Legenda {
  /** `lista`: uma linha por item, com uma barra proporcional à contagem (em vez dos itens lado a lado). */
  constructor({ porPartido = false, lista = false } = {}) {
    this.porPartido = porPartido;
    this.lista = lista;
    this.el = h("ul", { class: lista ? "legenda legenda--lista" : "legenda", "aria-label": "Legenda do mapa" });
  }

  atualizar(ufs) {
    const grupos = new Map();
    let semVotos = 0;
    for (const l of ufs) {
      if (l.codigo === "zz") continue; // o exterior não é UF: aparece no mapa, mas não entra na contagem
      const lider = liderDaUf(l);
      if (!lider) {
        semVotos++;
        continue;
      }
      const chave = this.porPartido ? lider.partido : lider.sq;
      const g = grupos.get(chave) || { cor: corDe(lider, this.porPartido), rotulo: this.porPartido ? lider.partido : fmt.nome(lider.urna), partido: lider.partido, n: 0 };
      g.n++;
      grupos.set(chave, g);
    }
    const ordenados = [...grupos.values()].sort((a, b) => b.n - a.n || a.rotulo.localeCompare(b.rotulo, "pt-BR"));
    const maximo = Math.max(1, ...ordenados.map((g) => g.n), semVotos);
    const item = (cor, rotulo, n, detalhe) => {
      const barra = h("i");
      barra.style.width = `${(100 * n) / maximo}%`;
      return h("li", {}, h("span", { class: "chave", "data-cor": cor }), h("b", {}, quebravel(rotulo)),
        this.lista ? h("span", { class: "qtd-barra", "aria-hidden": "true", "data-cor": cor }, barra) : null,
        h("span", { class: "qtd", texto: `${detalhe}${n} ${n === 1 ? "UF" : "UFs"}` }));
    };
    limpar(this.el);
    for (const g of ordenados) this.el.append(item(g.cor, g.rotulo, g.n, this.porPartido ? "" : `${g.partido} · `));
    if (semVotos) {
      const vazio = item("neutro", "Sem votos apurados", semVotos, "");
      vazio.firstChild.className = "chave chave-vazia";
      vazio.firstChild.removeAttribute("data-cor");
      this.el.append(vazio);
    }
  }
}

// ---- tabela de UFs ---------------------------------------------------------------------------------------
const COLUNAS_ORDENAVEIS = {
  nome: (l) => l.nome,
  totalizado: (l) => (l.disponivel && l.secoes.pst ? l.secoes.pst.n : -1),
  margem: (l) => (l.margem_pp === null || l.margem_pp === undefined ? -1 : l.margem_pp),
};

export function celulaCandidato(c, comPartido) {
  if (!c) return h("td", {}, h("span", { class: "sem-valor", texto: "—" }));
  const cor = corDe(c, comPartido);
  // Nas tabelas que cruzam UFs com candidatos diferentes (Governador, Senador) quem identifica é o partido: a sigla
  // colorida acompanha o nome. No Presidente os candidatos são os mesmos em toda linha, então basta o quadradinho de cor.
  const marca = comPartido ? h("span", { class: "sigla", "data-cor": cor, texto: c.partido }) : h("span", { class: "chave", "data-cor": cor });
  return h("td", {}, h("span", { class: "nome-cor" }, marca, comPartido ? fmt.nome(c.urna) : quebravel(c.urna), " ", h("span", { class: "pct", texto: fmt.pct(c.pct) })));
}

export class TabelaUfs {
  /**
   * `posicoes`: quantos colocados mostrar por linha (2 = 1º e 2º; 3 = Senador).
   * `vagas`: vagas em disputa por UF (a diferença é medida entre a última vaga e o primeiro fora dela).
   * `comPartido`: mostra a sigla do partido junto de cada candidato (tabelas que cruzam UFs com candidatos diferentes).
   */
  constructor({ posicoes = 2, vagas = 1, comPartido = false } = {}) {
    this.posicoes = posicoes;
    this.vagas = vagas;
    this.comPartido = comPartido;
    this.ordem = { chave: "nome", dir: 1 };
    this.linhas = [];
    this.corpo = h("tbody");
    this.cabecalho = h("tr");
    this.el = h("table", { class: "tabela" }, h("thead", {}, this.cabecalho), this.corpo);
    this.montarCabecalho();
  }

  th(rotulo, chave, classe, ajuda) {
    const conteudo = chave
      ? h("button", { class: "th-botao", type: "button", onclick: () => this.ordenarPor(chave) }, rotulo, this.ordem.chave === chave ? (this.ordem.dir > 0 ? " ▲" : " ▼") : "")
      : rotulo;
    return h("th", { class: classe || null, title: ajuda || null, scope: "col", "aria-sort": chave && this.ordem.chave === chave ? (this.ordem.dir > 0 ? "ascending" : "descending") : null }, conteudo);
  }

  montarCabecalho() {
    const multiplas = this.vagas > 1;
    const rotulo = (posicao) => `${posicao}º colocado${multiplas && posicao > this.vagas ? " (fora das vagas)" : ""}`;
    const ajudaDiferenca = multiplas
      ? `Diferença entre o ${this.vagas}º colocado (última vaga) e o ${this.vagas + 1}º (primeiro fora das vagas), calculada pelo painel a partir dos percentuais do TSE`
      : "Diferença entre o 1º e o 2º colocados, calculada pelo painel a partir dos percentuais do TSE";
    limpar(this.cabecalho).append(
      this.th("UF", "nome"),
      this.th("Totalizado", "totalizado", null, "Percentual das seções totalizadas"),
      this.th(rotulo(1)),
      ...Array.from({ length: this.posicoes - 1 }, (_, i) => this.th(rotulo(i + 2), null, "esconde-movel")),
      this.th("Diferença", "margem", "num", ajudaDiferenca),
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
    const valor = COLUNAS_ORDENAVEIS[this.ordem.chave];
    const ordenadas = [...this.linhas].sort((a, b) => {
      const va = valor(a), vb = valor(b);
      const cmp = typeof va === "string" ? va.localeCompare(vb, "pt-BR") : va - vb;
      return cmp * this.ordem.dir || a.nome.localeCompare(b.nome, "pt-BR");
    });
    limpar(this.corpo);
    for (const l of ordenadas) {
      const nome = l.codigo === "zz"
        ? h("span", { class: "linha-link", texto: l.nome })
        : h("a", { class: "linha-link", href: `/uf/${l.codigo}${window.location.search}`, texto: l.nome });
      if (!l.disponivel) {
        this.corpo.append(h("tr", {}, h("td", {}, nome),
          h("td", { colspan: String(this.posicoes + 2) }, h("span", { class: "sem-valor", texto: "Aguardando dados do TSE" }))));
        continue;
      }
      const medidor = h("span", { class: "mini-medidor", "aria-hidden": "true" }, h("span"));
      medidor.firstChild.style.width = `${Math.min(100, l.secoes.pst ? l.secoes.pst.n : 0)}%`;
      const celulas = [h("td", {}, nome), h("td", {}, medidor, fmt.pct(l.secoes.pst))];
      for (let i = 0; i < this.posicoes; i++) {
        const td = celulaCandidato(l.top[i], this.comPartido);
        if (i > 0) td.className = "esconde-movel";
        celulas.push(td);
      }
      const barra = h("i", { "aria-hidden": "true", "data-cor": l.top[0] ? corDe(l.top[0], this.comPartido) : null });
      barra.style.width = `${Math.min(36, Math.max(2, (l.margem_pp || 0) * 1.1))}px`;
      celulas.push(h("td", { class: "num" }, h("span", { class: "margem" }, l.margem_pp === null || l.margem_pp === undefined ? null : barra, fmt.pontos(l.margem_pp))));
      this.corpo.append(h("tr", {}, ...celulas));
    }
  }
}
