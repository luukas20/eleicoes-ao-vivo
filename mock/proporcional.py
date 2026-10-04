"""Deputados SIMULADOS: EA20 de cargo proporcional (Federal, Estadual e Distrital) com a mesma estrutura do TSE.

Partidos isolados e federações (`agr[]`), vagas provisórias por agrupamento (`vag`, recalculadas a cada etapa
pelo método D'Hondt), quociente eleitoral (`qe`) e candidatos com votos. A situação de cada candidato (`e`, `st`)
só é preenchida na totalização final, como no feed real. Tudo fictício: nomes inventados, siglas reais só com
`partidos_reais` (para ensaiar as cores do painel).
"""
from __future__ import annotations

import random

from . import gerador
from .gerador import Simulacao, bloco_e, bloco_s, bloco_v, pct

# Cadeiras na Câmara por UF (soma 513). Estadual: 3x até 12 federais, depois 36 + o que passar de 12; o DF elege 24 distritais.
VAGAS_FEDERAL = {
    "ac": 8, "al": 9, "am": 8, "ap": 8, "ba": 39, "ce": 22, "df": 8, "es": 10, "go": 17, "ma": 18, "mg": 53, "ms": 8, "mt": 8,
    "pa": 17, "pb": 12, "pe": 25, "pi": 10, "pr": 30, "rj": 46, "rn": 8, "ro": 8, "rr": 8, "rs": 31, "sc": 16, "se": 8, "sp": 70, "to": 8,
}
NOMES_CARGO = {
    6: ("Deputado Federal", "Deputado Federal", "Deputada Federal"),
    7: ("Deputado Estadual", "Deputado Estadual", "Deputada Estadual"),
    8: ("Deputado Distrital", "Deputado Distrital", "Deputada Distrital"),
}
PARTE_DA_LEGENDA = 0.08  # fatia dos votos válidos que vai para a legenda (o resto é nominal)
SUPLENTES_NA_LISTA = 5

# (tipo, composição, nome da agregação, nº da federação ou "", [(sigla, nº do partido, nome)])
AGRUPAMENTOS_REAIS = [
    ("i", "PL", "PARTIDO LIBERAL", "", [("PL", 22, "PARTIDO LIBERAL")]),
    ("f", "PCDOB / PT / PV", "FEDERAÇÃO BRASIL DA ESPERANÇA", "101", [("PT", 13, "PARTIDO DOS TRABALHADORES"), ("PCDOB", 65, "PARTIDO COMUNISTA DO BRASIL"), ("PV", 43, "PARTIDO VERDE")]),
    ("f", "PP / UNIÃO", "FEDERAÇÃO UNIÃO PROGRESSISTA", "104", [("UNIÃO", 44, "UNIÃO BRASIL"), ("PP", 11, "PROGRESSISTAS")]),
    ("i", "PSD", "PARTIDO SOCIAL DEMOCRÁTICO", "", [("PSD", 55, "PARTIDO SOCIAL DEMOCRÁTICO")]),
    ("i", "MDB", "MOVIMENTO DEMOCRÁTICO BRASILEIRO", "", [("MDB", 15, "MOVIMENTO DEMOCRÁTICO BRASILEIRO")]),
    ("i", "REPUBLICANOS", "REPUBLICANOS", "", [("REPUBLICANOS", 10, "REPUBLICANOS")]),
    ("f", "CIDADANIA / PSDB", "FEDERAÇÃO PSDB CIDADANIA", "100", [("PSDB", 45, "PARTIDO DA SOCIAL DEMOCRACIA BRASILEIRA"), ("CIDADANIA", 23, "CIDADANIA")]),
    ("i", "PSB", "PARTIDO SOCIALISTA BRASILEIRO", "", [("PSB", 40, "PARTIDO SOCIALISTA BRASILEIRO")]),
    ("f", "PSOL / REDE", "FEDERAÇÃO PSOL REDE", "102", [("PSOL", 50, "PARTIDO SOCIALISMO E LIBERDADE"), ("REDE", 18, "REDE SUSTENTABILIDADE")]),
    ("i", "PDT", "PARTIDO DEMOCRÁTICO TRABALHISTA", "", [("PDT", 12, "PARTIDO DEMOCRÁTICO TRABALHISTA")]),
    ("i", "NOVO", "PARTIDO NOVO", "", [("NOVO", 30, "PARTIDO NOVO")]),
    ("i", "PODE", "PODEMOS", "", [("PODE", 20, "PODEMOS")]),
    ("f", "PRD / SOLIDARIEDADE", "FEDERAÇÃO RENOVAÇÃO SOLIDÁRIA", "103", [("PRD", 25, "PARTIDO RENOVAÇÃO DEMOCRÁTICA"), ("SOLIDARIEDADE", 77, "SOLIDARIEDADE")]),
    ("i", "AVANTE", "AVANTE", "", [("AVANTE", 70, "AVANTE")]),
]
NOMES = ("ALICE", "BENTO", "CORA", "DAVI", "ELIS", "FAUSTO", "GAL", "HELIO", "IRIS", "JONAS", "KATIA", "LEO", "MARA", "NILO", "OLGA",
         "PAULO", "RUI", "SONIA", "TEO", "UMA")
SOBRENOMES = ("ALVORADA", "BRISA", "COLINA", "DUNAS", "ESTRELA", "FONTE", "GRUTA", "HORIZONTE", "ILHA", "JARDIM", "LAGOA", "MARE")


def agrupamentos_simulados(real: bool) -> list[tuple]:
    """Os 14 agrupamentos da simulação: siglas reais (`partidos_reais`) ou fictícias, com 4 ou 3 federações."""
    if real:
        return AGRUPAMENTOS_REAIS
    saida = []
    for i in range(14):
        sigla = f"PS{i + 1:02d}"
        saida.append(("i", sigla, f"PARTIDO SIMULADO {i + 1:02d}", "", [(sigla, 60 + i, f"PARTIDO SIMULADO {i + 1:02d}")]))
    for a, b, numero in ((1, 2, "901"), (5, 6, "902"), (9, 10, "903")):  # três federações fictícias
        sa, sb = f"PS{a + 1:02d}", f"PS{b + 1:02d}"
        saida[a] = ("f", f"{sa} / {sb}", f"FEDERAÇÃO SIMULADA {numero}", numero,
                    [(sa, 60 + a, f"PARTIDO SIMULADO {a + 1:02d}"), (sb, 60 + b, f"PARTIDO SIMULADO {b + 1:02d}")])
        saida[b] = ("i", f"PS{b + 1:02d}X", f"PARTIDO SIMULADO {b + 1:02d}X", "", [(f"PS{b + 1:02d}X", 80 + b, f"PARTIDO SIMULADO {b + 1:02d}X")])
    return saida


def vagas(cargo: int, uf: str) -> int:
    federal = VAGAS_FEDERAL[uf]
    if cargo == 6:
        return federal
    if cargo == 8:
        return 24
    return 3 * federal if federal <= 12 else 36 + (federal - 12)


def _dhondt(votos: list[int], cadeiras: int, teto: list[int]) -> list[int]:
    """Método D'Hondt com limite de cadeiras por agrupamento (não pode eleger mais do que tem candidatos)."""
    vag = [0] * len(votos)
    for _ in range(cadeiras):
        candidatos = [i for i in range(len(votos)) if vag[i] < teto[i]]
        if not candidatos or max(votos) <= 0:
            break
        melhor = max(candidatos, key=lambda i: (votos[i] / (vag[i] + 1), -i))
        vag[melhor] += 1
    return vag


def _candidatos_do_agrupamento(cargo: int, uf: str, idx: int, partes: list[tuple], quantos: int) -> list[dict]:
    """Candidatos fictícios do agrupamento, alternando os partidos da federação. Pesos de voto estilo "puxador" (Zipf)."""
    rnd = random.Random(f"cand:{cargo}:{uf}:{idx}")
    uf_idx = gerador.TODAS_ABRANGENCIAS.index(uf)
    saida = []
    for k in range(quantos):
        sigla, numero_partido, _nome = partes[k % len(partes)]
        nome = f"{NOMES[(idx * 7 + k * 3) % len(NOMES)]} {SOBRENOMES[(idx + k * 5) % len(SOBRENOMES)]}"
        anulado = idx == 1 and k == quantos - 1  # um por lista: candidatura indeferida, com os votos "anulados sub judice"
        if anulado:
            nome = "NILO INDEFERIDO"
        numero = numero_partido * (100 if cargo == 6 else 1000) + (k // len(partes)) + 1
        saida.append({
            "sq": int(f"91{cargo:02d}{uf_idx:02d}{idx:02d}{k:03d}"), "n": numero, "nm": f"{nome} (SIMULADO)", "nmu": nome, "sigla": sigla,
            "peso": (1 / (k + 1) ** 1.15) * rnd.uniform(0.7, 1.3), "anulado": anulado,
        })
    return saida


def resultado_proporcional(sim: Simulacao, ele: int, cargo: int, uf: str) -> dict:
    """EA20 simulado de um cargo proporcional numa UF (Federal e Estadual: as 27 menos DF; Distrital: só o DF)."""
    p = sim.passo()
    agg = sim.agregado(cargo, uf, None, p)
    terminou = sim.terminou(uf, None, p)
    final = terminou and agg.st > 0
    dg, hg = sim.carimbo(p)
    dt, ht = ("", "") if agg.st == 0 else (dg, hg)
    cadeiras = vagas(cargo, uf)
    grupos = agrupamentos_simulados(sim.partidos_reais)
    votos_agr = list(agg.votos)
    vv = sum(votos_agr)

    # candidatos de cada agrupamento e votos nominais repartidos entre eles
    quantos = [max(4, cadeiras // 3 + 2 + (2 if g[0] == "f" else 0)) for g in grupos]
    listas = [_candidatos_do_agrupamento(cargo, uf, i, [(s, n, nm) for s, n, nm in g[4]], quantos[i]) for i, g in enumerate(grupos)]
    legenda = [round(v * PARTE_DA_LEGENDA) for v in votos_agr]
    nominais = [v - lg for v, lg in zip(votos_agr, legenda)]
    for i, lista in enumerate(listas):
        for c, v in zip(lista, gerador.repartir(nominais[i], [c["peso"] for c in lista])):
            c["votos"] = v

    vag = _dhondt(votos_agr, cadeiras, quantos) if agg.st > 0 and vv > 0 else [0] * len(grupos)
    qe = vv // cadeiras if (agg.st > 0 and vv > 0) else 0

    # situação dos candidatos: só na totalização final
    for i, lista in enumerate(listas):
        ordem = sorted(lista, key=lambda c: (-c["votos"], c["sq"]))
        qp = min(vag[i], votos_agr[i] // qe) if qe else 0
        for pos, c in enumerate(ordem):
            c["e"], c["st"] = "n", ""
            if final:
                if pos < qp:
                    c["e"], c["st"] = "s", "Eleito por QP"
                elif pos < vag[i]:
                    c["e"], c["st"] = "s", "Eleito por média"
                elif pos < vag[i] + SUPLENTES_NA_LISTA:
                    c["st"] = "Suplente"
                else:
                    c["st"] = "Não eleito"

    iniciou = agg.st > 0

    def cand_json(c: dict, seq: int) -> dict:
        txt, n9 = pct(c["votos"], vv)
        saida = {"n": str(c["n"]), "sqcand": str(c["sq"]), "nm": c["nm"], "nmu": c["nmu"], "dt": "01/01/1970", "seq": str(seq),
                 "e": c["e"], "st": c["st"], "vap": str(c["votos"]), "pvap": txt, "pvapn": n9}
        if iniciou:
            saida["dvt"] = "Anulado sub judice" if c.get("anulado") else "Válido"
        return saida

    agr_json = []
    for i, (tipo, composicao, nome, numero_fed, partes) in enumerate(grupos):
        pars = []
        for sigla, n_partido, nome_partido in partes:
            proprios = [c for c in listas[i] if c["sigla"] == sigla]
            soma = sum(c["votos"] for c in proprios)
            par = {"n": str(n_partido), "sg": sigla, "nm": nome_partido, "nfed": numero_fed, "tvtn": str(soma), "tvtl": "0", "tval": "0",
                   "tvan": str(soma), "cand": [cand_json(c, 500 + j) for j, c in enumerate(proprios)]}
            pars.append(par)
        if tipo == "i":  # partido isolado: os totais ficam no partido; a legenda vai toda para ele
            pars[0]["tvtl"] = pars[0]["tval"] = str(legenda[i])
        agr = {"n": f"2500{uf_idx_dos_arquivos(uf):02d}{i:04d}", "nm": nome, "tp": tipo, "com": composicao, "vag": str(vag[i]), "par": pars}
        if tipo == "f":
            agr.update({"tvtn": str(nominais[i]), "tvtl": str(legenda[i]), "tvan": str(nominais[i]), "tval": str(legenda[i])})
        agr_json.append(agr)

    nome_n, nome_m, nome_f = NOMES_CARGO[cargo]
    dados: dict = {
        "ele": str(ele), "t": "1", "f": "s", "sup": "n", "tpabr": "uf", "cdabr": uf, "dg": dg, "hg": hg, "idg": str(1000000 + p),
        "dt": dt, "ht": ht, "dv": "s", "tf": "s" if final else "n", "and": gerador._andamento(agg, terminou),
    }
    if final:
        dados["esae"], dados["mnae"] = "n", []
    dados["carg"] = [{
        "cd": str(cargo), "nmn": nome_n, "nmm": nome_m, "nmf": nome_f, "nv": str(cadeiras), "qe": str(qe),
        "fed": [{"n": g[3], "nm": g[2], "sg": "/".join(s for s, _n, _nm in g[4]), "com": "/".join(s for s, _n, _nm in g[4]),
                 "npar": [str(n) for _s, n, _nm in g[4]]} for g in grupos if g[0] == "f"],
        "agr": agr_json,
    }]
    dados["s"] = bloco_s(agg.ts, agg.st, agg.st)
    dados["e"] = bloco_e(agg.te, agg.est, agg.c)
    bloco = bloco_v(vv, agg.vb, agg.vn)
    bloco["vnom"], bloco["vl"] = str(sum(nominais)), str(sum(legenda))
    gerador._par(bloco, "pvnom", sum(nominais), vv)
    gerador._par(bloco, "pvl", sum(legenda), vv)
    dados["v"] = bloco
    return dados


def uf_idx_dos_arquivos(uf: str) -> int:
    return gerador.TODAS_ABRANGENCIAS.index(uf)
