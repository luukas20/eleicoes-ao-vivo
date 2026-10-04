// Placar de uma disputa: manchete gerada a partir dos números, duelo dos primeiros colocados (com foto)
// e uma faixa que mostra, de ponta a ponta, quem tem quanto dos votos válidos.
//
// Cada tile do duelo é criado uma vez por "posição" (1º, 2º...) e reaproveitado: quando dois candidatos trocam de
// lugar, só o conteúdo muda. A faixa, ao contrário, mantém um segmento por candidato, para ele deslizar em vez de piscar.
import { definirTexto, h, icone, limpar, piscar } from "./dom.js";
import * as fmt from "./fmt.js";

const SEGMENTOS_NA_FAIXA = 4;   // candidatos com segmento próprio na faixa; o resto vira "demais"

/** Texto da manchete e da linha de apoio, conforme o estado da apuração. Nunca inventa número. */
export function manchete(r) {
  const e = r.estado;
  const cand = r.candidatos;
  const vagas = (r.cargo && r.cargo.vagas) || 1;
  const a = cand[0];
  const comVotos = !!a && a.votos > 0;
  const cargo = r.cargo ? r.cargo.nome : "A disputa";
  if (!e.divulga) {
    return {
      titulo: "Votos ainda não liberados",
      sub: r.cargo && r.cargo.cd === 1
        ? "O TSE só libera os votos do Presidente a partir das 17h (horário de Brasília). Seções e eleitorado já aparecem."
        : "O TSE ainda não liberou os votos desta disputa. Seções e eleitorado já aparecem.",
    };
  }
  if (r.secoes.st === 0 || !comVotos) {
    return { titulo: "A apuração ainda não começou", sub: `Os números de ${cargo.toLowerCase()} aparecem assim que as primeiras urnas forem totalizadas.` };
  }
  // quem o próprio TSE já marcou: eleito, ou classificado para o 2º turno (vale mais que a posição no ranking)
  const ganhadores = cand.filter((c) => c.eleito && /^eleit/i.test(c.situacao || ""));
  const noSegundo = cand.filter((c) => c.eleito && /2º turno/i.test(c.situacao || ""));
  const nome = fmt.nome(a.urna);
  const b = cand[1];
  if (vagas === 1 && (e.definido === "e" || ganhadores.length)) {
    const v = ganhadores[0] || a;
    return { titulo: `${fmt.nome(v.urna)} vence a eleição`, sub: `${fmt.pct(v.pct)} dos votos válidos.${e.totalizacao_final ? "" : " A totalização final ainda confirma o resultado."}` };
  }
  if (e.definido === "s" || noSegundo.length >= 2) {
    const [x, y] = noSegundo.length >= 2 ? noSegundo : [a, b];
    return { titulo: "Haverá segundo turno", sub: y ? `Disputa entre ${fmt.nome(x.urna)} (${fmt.pct(x.pct)}) e ${fmt.nome(y.urna)} (${fmt.pct(y.pct)}).` : "" };
  }
  if (vagas > 1 && b) {
    if (ganhadores.length >= vagas) {
      return { titulo: `${fmt.nome(ganhadores[0].urna)} e ${fmt.nome(ganhadores[1].urna)} são eleitos`, sub: `${fmt.pct(ganhadores[0].pct)} e ${fmt.pct(ganhadores[1].pct)} dos votos.` };
    }
    const c = cand[vagas];
    const folga = c ? ` ${fmt.pontos(b.pct.n - c.pct.n)} sobre ${fmt.nome(c.urna)}, o primeiro fora das vagas.` : "";
    return { titulo: `${nome} e ${fmt.nome(b.urna)} ocupam as ${vagas} vagas`, sub: `${fmt.pct(a.pct)} e ${fmt.pct(b.pct)}.${folga}` };
  }
  const folga = b ? `${fmt.pontos(a.pct.n - b.pct.n)} à frente de ${fmt.nome(b.urna)}` : "";
  return { titulo: `${nome} lidera com ${fmt.pct(a.pct)}`, sub: [folga, `${fmt.pct(r.secoes.pst)} das seções apuradas`].filter(Boolean).join(" · ") };
}

export class Placar {
  /** `rotulo`: linha acima da manchete; `nivel`: nível do título (1 na página inicial, 2 dentro de abas); `metaCinquenta`: marca os 50%. */
  constructor({ rotulo = "", nivel = 1, metaCinquenta = false } = {}) {
    this.metaCinquenta = metaCinquenta;
    this.kicker = h("p", { class: "kicker", texto: rotulo });
    this.titulo = h(`h${nivel}`, { class: "manchete", texto: "Carregando a apuração…" });
    this.sub = h("p", { class: "manchete-sub", hidden: true });
    this.duelo = h("ol", { class: "duelo", hidden: true });
    this.slots = [];
    this.faixa = h("div", { class: "faixa", role: "img" });
    this.meta = h("div", { class: "faixa-meta", "aria-hidden": "true", hidden: !metaCinquenta }, h("span", { texto: "50%" }));
    this.leg = h("ul", { class: "faixa-leg" });
    this.segmentos = new Map();
    this.blocoFaixa = h("div", { class: "faixa-bloco", hidden: true }, this.faixa, this.meta, this.leg);
    this.el = h("div", { class: "placar" }, this.kicker, this.titulo, this.sub, this.duelo, this.blocoFaixa);
    this.chave = null;
  }

  criarSlot() {
    const s = {};
    s.foto = h("img", { class: "duelo-foto", alt: "", width: "92", height: "129", decoding: "async" });
    s.sigla = h("span", { class: "sigla" });
    s.numero = h("span", { class: "numero" });
    s.pos = h("span", { class: "duelo-pos", "aria-hidden": "true" });
    s.selo = h("span", { class: "selo", hidden: true });
    s.nome = h("p", { class: "duelo-nome" });
    s.vice = h("p", { class: "duelo-vice" });
    s.pct = h("p", { class: "duelo-pct" });
    s.votos = h("p", { class: "duelo-votos" });
    s.el = h("li", { class: "duelo-card" },
      s.foto,
      h("div", { class: "duelo-info" }, h("div", { class: "duelo-linha" }, s.sigla, s.numero, s.selo, s.pos), s.nome, s.vice),
      s.pct, s.votos);
    return s;
  }

  preencherSlot(s, c, posicao, r) {
    if (s.foto.getAttribute("src") !== c.foto) s.foto.src = c.foto;
    s.el.dataset.cor = c.cor;
    s.el.dataset.lider = String(posicao === 0);
    s.sigla.textContent = c.partido;
    s.numero.textContent = c.numero;
    s.pos.textContent = `${posicao + 1}º`;
    s.nome.textContent = c.urna;
    s.vice.textContent = c.vice ? `Vice: ${c.vice}` : "";
    s.vice.hidden = !c.vice;
    if (s.ultimoPct !== undefined && s.ultimoPct !== c.pct.t && s.ultimoSq === c.sq) piscar(s.pct);
    s.ultimoPct = c.pct.t;
    s.ultimoSq = c.sq;
    limpar(s.pct).append(c.pct.t, h("small", { texto: "%" }));
    definirTexto(s.votos, `${fmt.inteiro(c.votos)} votos`);
    if (c.eleito) {
      const rotulo = c.situacao || (r.estado.definido === "s" ? "2º turno" : "Eleito");
      limpar(s.selo).append(icone(/^Eleit/.test(rotulo) ? "ok" : "info"), rotulo);
      s.selo.hidden = false;
    } else {
      s.selo.hidden = true;
    }
    s.el.setAttribute("aria-label", `${posicao + 1}º colocado: ${c.urna}, ${c.partido}, ${fmt.pct(c.pct)} dos votos, ${fmt.inteiro(c.votos)} votos`);
  }

  atualizar(r) {
    const { titulo, sub } = manchete(r);
    this.titulo.textContent = titulo;
    this.sub.textContent = sub;
    const iniciou = r.estado.divulga && r.secoes.st > 0 && r.candidatos.some((c) => c.votos > 0);
    this.duelo.hidden = !iniciou;
    this.blocoFaixa.hidden = !iniciou;
    this.sub.hidden = !sub;
    if (!iniciou) return;

    const vagas = (r.cargo && r.cargo.vagas) || 1;
    const quantos = Math.min(Math.max(2, vagas), r.candidatos.length);
    this.duelo.style.setProperty("--n", String(quantos));
    while (this.slots.length < quantos) {
      const s = this.criarSlot();
      this.slots.push(s);
      this.duelo.append(s.el);
    }
    this.slots.forEach((s, i) => {
      s.el.hidden = i >= quantos;
      if (i < quantos) this.preencherSlot(s, r.candidatos[i], i, r);
    });
    this.pintarFaixa(r, quantos);
  }

  /** Um segmento por candidato (os primeiros) e um "demais"; a largura é o percentual publicado, do TSE. */
  pintarFaixa(r, quantos) {
    const proprios = r.candidatos.slice(0, Math.max(SEGMENTOS_NA_FAIXA, quantos));
    const demais = r.candidatos.slice(proprios.length);
    const somaDemais = demais.reduce((t, c) => t + c.pct.n, 0);
    const vistos = new Set();
    const ordem = [];
    for (const c of proprios) {
      vistos.add(c.sq);
      let seg = this.segmentos.get(c.sq);
      if (!seg) {
        seg = h("span");
        this.segmentos.set(c.sq, seg);
      }
      seg.dataset.cor = c.cor;
      seg.style.flexGrow = String(Math.max(c.pct.n, 0));
      ordem.push(seg);
    }
    let segDemais = this.segmentos.get("demais");
    if (!segDemais) {
      segDemais = h("span", { "data-cor": "neutro" });
      this.segmentos.set("demais", segDemais);
    }
    segDemais.style.flexGrow = String(Math.max(somaDemais, 0));
    segDemais.hidden = demais.length === 0;
    ordem.push(segDemais);
    for (const [chave, seg] of this.segmentos) if (chave !== "demais" && !vistos.has(chave)) { seg.remove(); this.segmentos.delete(chave); }
    const atuais = [...this.faixa.children];
    if (atuais.length !== ordem.length || ordem.some((s, i) => atuais[i] !== s)) this.faixa.replaceChildren(...ordem);

    // legenda só do que a faixa mostra além dos tiles (os tiles já identificam os primeiros)
    limpar(this.leg);
    for (const c of proprios.slice(quantos)) {
      this.leg.append(h("li", {}, h("span", { class: "chave", "data-cor": c.cor }), h("span", { texto: fmt.nome(c.urna) }), h("b", { texto: fmt.pct(c.pct) })));
    }
    if (demais.length) {
      this.leg.append(h("li", {}, h("span", { class: "chave", "data-cor": "neutro" }),
        h("span", { texto: `Demais (${demais.length})` }), h("b", { texto: fmt.pct2(somaDemais) })));
    }
    const resumo = proprios.map((c) => `${fmt.nome(c.urna)} ${fmt.pct(c.pct)}`);
    if (demais.length) resumo.push(`demais ${fmt.pct2(somaDemais)}`);
    this.faixa.setAttribute("aria-label", `Participação nos votos válidos: ${resumo.join("; ")}`);
  }
}
