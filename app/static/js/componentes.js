// Componentes de interface. Cada um cria seu nó uma vez (`el`) e se atualiza com `atualizar(...)`,
// reaproveitando os elementos para as barras e os blocos animarem em vez de piscar.
import { h, icone, limpar } from "./dom.js";
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

// Avisos que decorrem do estado de um resultado (Presidente, Governador, Senador...).
export function avisosDoResultado(r) {
  const lista = [];
  const e = r.estado;
  const lider = r.candidatos[0] && r.candidatos[0].votos > 0 ? r.candidatos[0] : null;
  if (!e.divulga) {
    lista.push({
      tipo: "atencao", titulo: "Votação ainda não liberada.",
      texto: "O TSE só libera os votos do Presidente a partir das 17h (horário de Brasília). Seções e eleitorado já aparecem.",
    });
  } else if (r.secoes.st === 0) {
    lista.push({ tipo: "info", titulo: "Apuração ainda não iniciada.", texto: "Os números aparecem assim que as primeiras urnas forem totalizadas." });
  }
  if (e.definido === "e" && lider) {
    lista.push({ tipo: "ok", titulo: `${lider.urna} está eleito(a) matematicamente.`, texto: "A totalização final ainda confirma o resultado." });
  } else if (e.definido === "s") {
    const [a, b] = r.candidatos;
    lista.push({ tipo: "info", titulo: "Haverá segundo turno.", texto: a && b ? `Disputa entre ${a.urna} e ${b.urna}.` : "" });
  }
  if (e.totalizacao_final) lista.push({ tipo: "ok", titulo: "Totalização final concluída." });
  if (e.sem_eleito) lista.push({ tipo: "atencao", titulo: "Sem atribuição de eleito.", texto: (e.motivos || []).join(" ") });
  return lista;
}

// ---- herói: progresso da totalização -----------------------------------------------------------------
export class Heroi {
  constructor({ rotulo = "Seções totalizadas" } = {}) {
    const id = novoId("heroi");
    this.num = h("p", { class: "heroi-num" });
    this.preench = h("span");
    this.medidor = h("div", { class: "medidor", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100" }, this.preench);
    this.sub = h("p", { class: "sub" });
    this.el = h("section", { class: "cartao heroi", "aria-labelledby": id },
      h("p", { class: "rotulo", id, texto: rotulo }), this.num, this.medidor, this.sub);
  }

  atualizar(r) {
    const s = r.secoes;
    const texto = s.pst ? s.pst.t : "0,00";
    const n = s.pst ? s.pst.n : 0;
    limpar(this.num).append(texto, h("small", { texto: "%" }));
    this.preench.style.width = `${Math.min(100, Math.max(0, n))}%`;
    this.medidor.setAttribute("aria-valuenow", String(Math.round(n)));
    this.medidor.setAttribute("aria-label", `${texto}% das seções totalizadas`);
    const partes = [`${fmt.inteiro(s.st)} de ${fmt.inteiro(s.ts)} seções`];
    partes.push(r.totalizado_em ? `última totalização às ${fmt.hora(r.totalizado_em)} (horário de Brasília)` : "apuração ainda não iniciada");
    this.sub.textContent = partes.join(" · ");
  }
}

// ---- KPIs --------------------------------------------------------------------------------------------
const KPIS = [
  ["eleitorado", "Eleitorado", "Eleitores aptos a votar na abrangência"],
  ["comparecimento", "Comparecimento", "Percentual sobre os eleitores das seções instaladas"],
  ["abstencao", "Abstenção", "Percentual sobre os eleitores das seções instaladas"],
  ["brancos", "Votos em branco", "Percentual sobre o total de votos"],
  ["nulos", "Votos nulos", "Percentual sobre o total de votos"],
];

export class Kpis {
  constructor() {
    this.refs = {};
    this.el = h("div", { class: "kpis" });
    for (const [chave, rotulo, ajuda] of KPIS) {
      const valor = h("p", { class: "kpi-valor" });
      const sub = h("p", { class: "kpi-sub" });
      this.refs[chave] = { valor, sub };
      this.el.append(h("div", { class: "kpi", title: ajuda }, h("p", { class: "rotulo", texto: rotulo }), valor, sub));
    }
  }

  definir(chave, valor, sub) {
    this.refs[chave].valor.textContent = valor;
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
    linha.foto = h("img", { class: "foto", alt: "", width: "40", height: "50", loading: "lazy", decoding: "async", src: c.foto });
    linha.nome = h("span", { class: "cand-nome" });
    linha.partido = h("span", { class: "cand-partido" });
    linha.selo = h("span", { class: "selo", hidden: true });
    linha.preench = h("span", { class: "barra-preench" });
    linha.extra = h("div", { class: "cand-extra" });
    linha.pct = h("strong", { class: "cand-pct" });
    linha.votos = h("span", { class: "cand-votos" });
    const barra = h("div", { class: "barra", "aria-hidden": "true" },
      h("span", { class: "barra-trilho" }), linha.preench, this.metaCinquenta ? h("span", { class: "barra-meta" }) : null);
    linha.el = h("li", { class: "cand", tabindex: "0" },
      linha.foto,
      h("div", {}, h("div", { class: "cand-topo" }, linha.nome, linha.partido, linha.selo), barra, linha.extra),
      h("div", { class: "cand-nums" }, linha.pct, linha.votos));
    dica.vincular(linha.el, () => this.dicaDe(linha.c));
    return linha;
  }

  dicaDe(c) {
    return h("div", {}, dica.titulo(`${c.urna} · ${c.partido} ${c.numero}`),
      dica.linha(c.cor, fmt.pct(c.pct), "dos votos"), dica.linha(c.cor, fmt.inteiro(c.votos), "votos"),
      h("div", { class: "dica-linha" }, h("span", { texto: c.nome })));
  }

  preencher(linha, c, iniciou, r) {
    linha.c = c;
    if (linha.foto.getAttribute("src") !== c.foto) linha.foto.src = c.foto;
    linha.nome.textContent = c.urna;
    linha.partido.textContent = `${c.partido} · ${c.numero}`;
    linha.pct.textContent = iniciou ? fmt.pct(c.pct) : "—";
    linha.votos.textContent = iniciou ? `${fmt.inteiro(c.votos)} votos` : "";
    linha.preench.dataset.cor = String(c.cor);
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
      this.preencher(linha, c, iniciou, r);
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
/** Candidato à frente na UF, ou null se ainda não há votos liberados. */
export function liderDaUf(l) {
  return l && l.disponivel && l.top.length ? l.top[0] : null;
}

/** Dica (tooltip) de uma UF: totalização e os primeiros colocados. */
export function dicaDeUf(l) {
  if (!l) return null;
  const corpo = h("div", {}, dica.titulo(l.nome));
  if (!l.disponivel) {
    corpo.append(h("div", { class: "dica-linha", texto: "Aguardando dados do TSE" }));
    return corpo;
  }
  corpo.append(h("div", { class: "dica-linha", texto: `${fmt.pct(l.secoes.pst)} das seções totalizadas` }));
  if (l.totalizado_em) corpo.append(h("div", { class: "dica-linha", texto: `Última totalização da UF às ${fmt.hora(l.totalizado_em)}` }));
  for (const c of l.top) corpo.append(dica.linha(c.cor, fmt.pct(c.pct), c.urna, `${fmt.inteiro(c.votos)} votos`));
  if (!l.top.length) corpo.append(h("div", { class: "dica-linha", texto: l.divulga ? "Sem votos apurados" : "Votação ainda não liberada" }));
  return corpo;
}

/** Texto lido por leitores de tela para uma UF (o nome é passado à parte porque o mapa já o conhece antes dos dados). */
export function descreverUf(nome, l) {
  const lider = liderDaUf(l);
  return lider
    ? `${nome}: ${lider.urna} à frente com ${fmt.pct(lider.pct)}; ${fmt.pct(l.secoes.pst)} das seções totalizadas`
    : `${nome}: ${l && l.disponivel && l.secoes.st > 0 ? "sem votos liberados" : "apuração não iniciada"}`;
}

// ---- mapa em blocos ------------------------------------------------------------------------------------
export const ORDEM_BLOCOS = [
  "rr", "ap", "am", "pa", "ma", "ce", "rn", "ac", "ro", "mt", "to", "pi", "pe", "pb",
  "ms", "go", "ba", "al", "df", "mg", "se", "pr", "sp", "rj", "es", "sc", "rs", "zz",
];

export class Mapa {
  constructor() {
    this.dados = new Map();
    this.blocos = new Map();
    this.el = h("div", { class: "mapa", role: "group", "aria-label": "Mapa de blocos das UFs, colorido pelo candidato que lidera" });
    for (const uf of ORDEM_BLOCOS) {
      const bloco = {};
      bloco.uf = h("b", { texto: uf === "zz" ? "EX" : uf.toUpperCase() });
      bloco.valor = h("span");
      bloco.prog = h("i");
      const filhos = [bloco.uf, bloco.valor, bloco.prog];
      bloco.el = uf === "zz"
        ? h("div", { class: `bloco uf-${uf}`, "data-uf": uf, tabindex: "0", role: "img" }, ...filhos)
        : h("a", { class: `bloco uf-${uf}`, "data-uf": uf, href: `/uf/${uf}${window.location.search}` }, ...filhos);
      dica.vincular(bloco.el, () => dicaDeUf(this.dados.get(uf)));
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
      if (lider) {
        b.el.dataset.cor = String(lider.cor);
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
  }
}

export class Legenda {
  constructor() {
    this.el = h("ul", { class: "legenda" });
  }

  atualizar(itens) {
    limpar(this.el);
    for (const i of itens) {
      this.el.append(h("li", {}, h("span", { class: "chave", "data-cor": String(i.cor) }), `${i.urna} (${i.numero})`));
    }
    this.el.append(
      h("li", {}, h("span", { class: "chave", "data-cor": "0" }), "Outros candidatos"),
      h("li", {}, h("span", { class: "chave chave-vazia" }), "Sem votos apurados"),
    );
  }
}

// ---- tabela de UFs ---------------------------------------------------------------------------------------
const COLUNAS_ORDENAVEIS = {
  nome: (l) => l.nome,
  totalizado: (l) => (l.disponivel && l.secoes.pst ? l.secoes.pst.n : -1),
  margem: (l) => (l.margem_pp === null || l.margem_pp === undefined ? -1 : l.margem_pp),
};

function celulaCandidato(c, semCor) {
  if (!c) return h("td", {}, h("span", { class: "sem-valor", texto: "—" }));
  // Em tabelas que cruzam UFs com candidatos diferentes (Governador, Senador) a cor não identifica
  // ninguém de uma linha para a outra, então não é usada: o nome e o partido é que identificam.
  const chave = semCor ? null : h("span", { class: "chave", "data-cor": String(c.cor) });
  const nome = semCor ? `${c.urna} (${c.partido})` : c.urna;
  return h("td", {}, h("span", { class: "nome-cor" }, chave, nome, " ", h("span", { class: "sub", texto: fmt.pct(c.pct) })));
}

export class TabelaUfs {
  /**
   * `posicoes`: quantos colocados mostrar por linha (2 = 1º e 2º; 3 = Senador).
   * `vagas`: vagas em disputa por UF (a diferença é medida entre a última vaga e o primeiro fora dela).
   * `semCor`: não colorir os candidatos (tabelas que cruzam UFs com candidatos diferentes).
   */
  constructor({ posicoes = 2, vagas = 1, semCor = false } = {}) {
    this.posicoes = posicoes;
    this.vagas = vagas;
    this.semCor = semCor;
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
        const td = celulaCandidato(l.top[i], this.semCor);
        if (i > 0) td.className = "esconde-movel";
        celulas.push(td);
      }
      celulas.push(h("td", { class: "num", texto: fmt.pontos(l.margem_pp) }));
      this.corpo.append(h("tr", {}, ...celulas));
    }
  }
}
