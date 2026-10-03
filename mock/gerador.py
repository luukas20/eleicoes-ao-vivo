"""Dados SIMULADOS no formato do TSE (EA11, EA12, EA14, EA20) para ensaiar o painel.

Tudo aqui é fictício — candidatos, partidos, votos — e sempre sai marcado como fase simulada
(`f = "s"`). A hierarquia é consistente: município -> UF -> Brasil (soma de baixo para cima),
e o resultado final de cada abrangência é determinístico (mesma semente, mesmo vencedor).
Os tamanhos (seções e eleitorado por UF) são os números reais do EA14 de 02/10/2026.

Cada arquivo é gerado a partir de UMA etapa (`passo`) lida uma única vez no começo, para os totais
nunca ficarem inconsistentes dentro da mesma resposta.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from app.tse.dominio import BRASIL, EXTERIOR, UF_NOMES, UFS

BRT = ZoneInfo("America/Sao_Paulo")
PASSOS = 150  # a simulação "totaliza" em 150 etapas; o conteúdo só muda de uma etapa para outra
N_MUNICIPIOS = 6  # municípios fictícios por UF (a capital + 5)

# (seções, eleitorado) por UF: números reais do EA14 de 02/10/2026
TAMANHOS: dict[str, tuple[int, int]] = {
    "ac": (2270, 613742), "al": (7101, 2442126), "am": (8157, 2798611), "ap": (1914, 576988),
    "ba": (35476, 11312752), "ce": (23765, 6996545), "df": (6969, 2258320), "es": (9844, 2991650),
    "go": (15686, 5080590), "ma": (18093, 5183115), "mg": (52062, 16372372), "ms": (7106, 2024430),
    "mt": (8287, 2637801), "pa": (20827, 6262397), "pb": (10712, 3248531), "pe": (21418, 7223450),
    "pi": (10225, 2704758), "pr": (27142, 8613657), "rj": (37675, 12857648), "rn": (8115, 2659825),
    "ro": (4698, 1265893), "rr": (1519, 401521), "rs": (27547, 8522545), "sc": (17326, 5734651),
    "se": (5923, 1740135), "sp": (103656, 34122892), "to": (4384, 1182023), "zz": (1351, 916534),
}
TODAS_ABRANGENCIAS = UFS + (EXTERIOR,)

# Candidatos FICTÍCIOS: (número, nome, nome na urna, sigla, partido, vice)
_POOL = [
    (10, "CANDIDATO ALFA SIMULADO", "ALFA", "PAL", "PARTIDO ALFA", "VICE DE ALFA"),
    (20, "CANDIDATA BETA SIMULADA", "BETA", "PBE", "PARTIDO BETA", "VICE DE BETA"),
    (30, "CANDIDATO GAMA SIMULADO", "GAMA", "PGA", "PARTIDO GAMA", "VICE DE GAMA"),
    (40, "CANDIDATA DELTA SIMULADA", "DELTA", "PDE", "PARTIDO DELTA", "VICE DE DELTA"),
    (50, "CANDIDATO ÉPSILON SIMULADO", "ÉPSILON", "PEP", "PARTIDO ÉPSILON", "VICE DE ÉPSILON"),
    (60, "CANDIDATA ZETA SIMULADA", "ZETA", "PZE", "PARTIDO ZETA", "VICE DE ZETA"),
]
N_CANDIDATOS = {1: 6, 3: 4, 5: 5}
ALFAS = {1: [6.0, 5.0, 2.0, 1.2, 0.8, 0.5], 3: [5.0, 4.0, 1.5, 0.8], 5: [4.0, 3.5, 3.0, 1.5, 0.8]}
VAGAS = {1: 1, 3: 1, 5: 2}
NOMES_CARGO = {
    1: ("Presidente", "Presidente", "Presidente"),
    3: ("Governador", "Governador", "Governadora"),
    5: ("Senador", "Senador", "Senadora"),
}

CONFIG_DIRS = [
    ("ft", "<base>/<ambiente>/<ciclo>/<cd_eleicao>/fotos/<uf>"),
    ("cm", "<base>/<ambiente>/<ciclo>/<cd_eleicao>/config"),
    ("e", "<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>"),
    ("cs", "<base>/<ambiente>/<ciclo>/arquivo-urna/<cd_pleito>/config/<uf>"),
    ("ab", "<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>"),
    ("u", "<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>"),
    ("aux", "<base>/<ambiente>/<ciclo>/arquivo-urna/<cd_pleito>/dados/<uf>/<municipio>/<zona>/<secao>"),
]


# ---- formatação como o TSE (tudo texto; percentuais com vírgula e gêmeo de 9 casas) --------------------
def pct(parte: int, total: int) -> tuple[str, str]:
    """(`"45,32"`, `"45.321234567"`); arredondamento half-up; 0 e 100 sem casas decimais no campo de 9 casas."""
    if total <= 0 or parte <= 0:
        return "0,00", "0"
    q = Decimal(parte) * 100 / Decimal(total)
    txt = f"{q.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}".replace(".", ",")
    nove = q.quantize(Decimal("0.000000001"), rounding=ROUND_HALF_UP)
    return txt, "100" if nove == 100 else f"{nove:f}"


def _par(destino: dict, chave: str, parte: int, total: int) -> None:
    txt, n9 = pct(parte, total)
    destino[chave], destino[chave + "n"] = txt, n9


def bloco_s(ts: int, st: int, sa: int) -> dict:
    snt, si, sni = ts - st, st, 0
    d: dict = {"ts": str(ts), "st": str(st)}
    _par(d, "pst", st, ts)
    d["snt"] = str(snt)
    _par(d, "psnt", snt, ts)
    d["si"] = str(si)
    _par(d, "psi", si, st)
    d["sni"] = str(sni)
    _par(d, "psni", sni, st)
    d["sa"] = str(sa)
    _par(d, "psa", sa, si)
    d["sna"] = str(si - sa)
    _par(d, "psna", si - sa, si)
    return d


def bloco_e(te: int, est: int, c: int) -> dict:
    esnt, esi, esni, esa = te - est, est, 0, est
    d: dict = {"te": str(te), "est": str(est)}
    _par(d, "pest", est, te)
    d["esnt"] = str(esnt)
    _par(d, "pesnt", esnt, te)
    d["esi"] = str(esi)
    _par(d, "pesi", esi, est)
    d["esni"] = str(esni)
    _par(d, "pesni", esni, est)
    d["esa"] = str(esa)
    _par(d, "pesa", esa, esi)
    d["esna"] = str(esi - esa)
    _par(d, "pesna", esi - esa, esi)
    d["c"] = str(c)
    _par(d, "pc", c, esi)
    d["a"] = str(esi - c)
    _par(d, "pa", esi - c, esi)
    return d


def bloco_v(vv: int, vb: int, vn: int) -> dict:
    tv = vv + vb + vn
    d: dict = {"tv": str(tv), "vvc": str(vv)}
    _par(d, "pvvc", vv, tv)
    d["vv"] = str(vv)
    _par(d, "pvv", vv, vv)
    d["vnom"] = str(vv)
    _par(d, "pvnom", vv, vv)
    for k in ("van", "vansj"):
        d[k] = "0"
        _par(d, "p" + k, 0, vv)
    d["vb"] = str(vb)
    _par(d, "pvb", vb, tv)
    d["tvn"] = str(vn)
    _par(d, "ptvn", vn, tv)
    d["vn"] = str(vn)
    _par(d, "pvn", vn, vn)
    d["vnt"] = "0"
    _par(d, "pvnt", 0, vn)
    d["vsan"], d["vscv"] = "0", "0"
    return d


# ---- agregação ---------------------------------------------------------------------------------------
@dataclass
class Agg:
    ts: int = 0
    st: int = 0
    te: int = 0
    est: int = 0
    c: int = 0
    vb: int = 0
    vn: int = 0
    votos: list[int] = field(default_factory=list)

    def somar(self, o: "Agg") -> None:
        for k in ("ts", "st", "te", "est", "c", "vb", "vn"):
            setattr(self, k, getattr(self, k) + getattr(o, k))
        if not self.votos:
            self.votos = [0] * len(o.votos)
        self.votos = [a + b for a, b in zip(self.votos, o.votos)]

    @property
    def vv(self) -> int:
        return sum(self.votos)


def repartir(total: int, pesos: list[float]) -> list[int]:
    """Divide `total` em inteiros proporcionais a `pesos` (maiores restos), somando exatamente `total`."""
    soma = sum(pesos) or 1.0
    bruto = [total * p / soma for p in pesos]
    base = [int(b) for b in bruto]
    resto = total - sum(base)
    for i in sorted(range(len(pesos)), key=lambda i: bruto[i] - base[i], reverse=True)[:resto]:
        base[i] += 1
    return base


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _suave(v: float) -> float:
    v = _clamp(v)
    return v * v * (3 - 2 * v)


class Simulacao:
    """Relógio e modelo da apuração simulada. Seguro para uso por várias threads.

    Os métodos de modelo recebem o `passo` explicitamente; os construtores de arquivo leem
    `passo()` uma vez e o repassam, garantindo coerência dentro de cada resposta.
    """

    def __init__(self, duracao_s: float = 600.0, velocidade: float = 1.0, inicio: float = 0.0, relogio=time.monotonic):
        self._relogio = relogio
        self._lock = threading.Lock()
        self.duracao_s = duracao_s
        self._velocidade = velocidade
        self._acumulado = inicio * duracao_s  # segundos simulados já decorridos
        self._desde = relogio()
        self._rodando = True
        self.dv_presidente = True
        self.falha_status: int | None = None
        self.falha_ate = 0.0
        self._cache: dict[tuple, Agg] = {}
        self._carimbos: dict[int, tuple[str, str]] = {}

    # ---- relógio ------------------------------------------------------------------------------------
    def _segundos(self) -> float:
        with self._lock:
            extra = (self._relogio() - self._desde) * self._velocidade if self._rodando else 0.0
            return self._acumulado + extra

    def x(self) -> float:
        """Progresso global (1.0 = fim da apuração)."""
        return self._segundos() / self.duracao_s

    def passo(self) -> int:
        return min(int(self.x() * PASSOS), int(1.2 * PASSOS))

    def pausar(self) -> None:
        with self._lock:
            if self._rodando:
                self._acumulado += (self._relogio() - self._desde) * self._velocidade
                self._rodando = False

    def retomar(self) -> None:
        with self._lock:
            if not self._rodando:
                self._desde, self._rodando = self._relogio(), True

    def velocidade(self, v: float) -> None:
        with self._lock:
            if self._rodando:
                self._acumulado += (self._relogio() - self._desde) * self._velocidade
                self._desde = self._relogio()
            self._velocidade = v

    def ir_para(self, x: float) -> None:
        with self._lock:
            self._acumulado, self._desde = x * self.duracao_s, self._relogio()

    def estado(self) -> dict:
        restante = max(0.0, self.falha_ate - self._relogio())
        return {
            "x": round(self.x(), 4), "passo": self.passo(), "duracao_s": self.duracao_s,
            "velocidade": self._velocidade, "rodando": self._rodando, "dv_presidente": self.dv_presidente,
            "falha": {"status": self.falha_status, "restante_s": round(restante, 1)} if restante > 0 else None,
        }

    def carimbo(self, passo: int) -> tuple[str, str]:
        """(data, hora) de geração, estáveis dentro de uma mesma etapa para o ETag não oscilar."""
        with self._lock:
            if passo not in self._carimbos:
                agora = datetime.now(BRT)
                self._carimbos[passo] = (agora.strftime("%d/%m/%Y"), agora.strftime("%H:%M:%S"))
            return self._carimbos[passo]

    # ---- modelo ---------------------------------------------------------------------------------------
    @staticmethod
    def progresso_uf(uf: str, passo: int) -> float:
        rnd = random.Random(f"perfil:{uf}")
        inicio, largura = rnd.uniform(0.0, 0.10), rnd.uniform(0.55, 0.85)
        return _suave((passo / PASSOS - inicio) / largura)

    @classmethod
    def progresso_mun(cls, uf: str, k: int, passo: int) -> float:
        return _clamp(cls.progresso_uf(uf, passo) * 1.25 - 0.25 * k / N_MUNICIPIOS)

    @staticmethod
    def candidatos(cargo: int, uf: str) -> list[tuple]:
        """Lista fictícia: (nº, nome, urna, sigla, partido, vice, sqcand). Presidente é igual em todo lugar."""
        idx = 0 if cargo == 1 else TODAS_ABRANGENCIAS.index(uf)
        saida = []
        for i, (n, nome, urna, sigla, partido, vice) in enumerate(_POOL[: N_CANDIDATOS[cargo]]):
            numero = n * 10 + 1 if cargo == 5 else n  # senador tem 3 dígitos
            saida.append((numero, nome, urna, sigla, partido, vice, int(f"9000{cargo:02d}{idx:02d}{i:02d}")))
        return saida

    @staticmethod
    def _pesos_base(cargo: int, uf: str) -> list[float]:
        rnd = random.Random(f"base:{cargo}:{uf}")
        alfas = list(ALFAS[cargo])
        if rnd.random() < 0.5:  # em algumas UFs o 2º colocado nacional lidera
            alfas[0], alfas[1] = alfas[1], alfas[0]
        return [rnd.gammavariate(a, 1.0) for a in alfas]

    def _pesos_mun(self, cargo: int, uf: str, k: int, pm: float) -> list[float]:
        base = self._pesos_base(cargo, uf)
        rnd = random.Random(f"mun:{cargo}:{uf}:{k}")
        vies = [rnd.uniform(-0.35, 0.35) for _ in base]  # viés da apuração: dissolve ao chegar a 100%
        ruido = [rnd.lognormvariate(0, 0.25) for _ in base]
        return [b * r * (1 + v * (1 - pm)) for b, r, v in zip(base, ruido, vies)]

    @staticmethod
    def _tamanho_mun(uf: str, k: int) -> tuple[int, int]:
        ts, te = TAMANHOS[uf]
        rnd = random.Random(f"tam:{uf}")
        outros = [rnd.uniform(0.5, 1.5) for _ in range(N_MUNICIPIOS - 1)]
        pesos = [0.28] + [0.72 * o / sum(outros) for o in outros]
        if k < N_MUNICIPIOS - 1:
            return round(ts * pesos[k]), round(te * pesos[k])
        return ts - sum(round(ts * p) for p in pesos[:-1]), te - sum(round(te * p) for p in pesos[:-1])

    def municipio(self, cargo: int, uf: str, k: int, passo: int) -> Agg:
        chave = (cargo, uf, k, passo)
        cache = self._cache.get(chave)
        if cache is not None:
            return cache
        if len(self._cache) > 20000:
            self._cache.clear()
        pm = self.progresso_mun(uf, k, passo)
        ts, te = self._tamanho_mun(uf, k)
        st, est = round(pm * ts), round(pm * te)
        comparecimento = 0.74 + 0.10 * random.Random(f"comp:{uf}:{k}").random()
        c = round(est * comparecimento)
        vb, vn = round(c * 0.02), round(c * 0.045)
        votos = repartir(c - vb - vn, self._pesos_mun(cargo, uf, k, pm))
        agg = Agg(ts, st, te, est, c, vb, vn, votos)
        self._cache[chave] = agg
        return agg

    def agregado(self, cargo: int, abr: str, mun: int | None, passo: int) -> Agg:
        """Agregado de um município (`mun`), de uma UF ou do Brasil (`abr='br'`, só Presidente)."""
        if mun is not None:
            return self.municipio(cargo, abr, self.indice_municipio(abr, mun), passo)
        total = Agg()
        if abr == BRASIL:
            for uf in TODAS_ABRANGENCIAS:
                total.somar(self.agregado(cargo, uf, None, passo))
        else:
            for k in range(N_MUNICIPIOS):
                total.somar(self.municipio(cargo, abr, k, passo))
        return total

    @staticmethod
    def codigo_municipio(uf: str, k: int) -> int:
        return 10000 + TODAS_ABRANGENCIAS.index(uf) * 100 + k

    @staticmethod
    def indice_municipio(uf: str, codigo: int) -> int:
        k = codigo - (10000 + TODAS_ABRANGENCIAS.index(uf) * 100)
        if not 0 <= k < N_MUNICIPIOS:
            raise KeyError(codigo)
        return k

    def terminou(self, abr: str, mun: int | None, passo: int) -> bool:
        if mun is not None:
            return self.progresso_mun(abr, self.indice_municipio(abr, mun), passo) >= 1.0
        if abr == BRASIL:
            return all(self.progresso_uf(u, passo) >= 1.0 for u in TODAS_ABRANGENCIAS)
        return self.progresso_uf(abr, passo) >= 1.0


# ---- construtores dos arquivos -----------------------------------------------------------------------
def _andamento(agg: Agg, terminou: bool) -> str:
    return "n" if agg.st == 0 else ("f" if terminou else "p")


def config_eleicoes(sim: Simulacao) -> dict:
    p = sim.passo()
    dg, hg = sim.carimbo(p)
    cp_geral = [(3, "Governador", "1"), (5, "Senador", "1"), (6, "Deputado Federal", "2"), (7, "Deputado Estadual", "2"), (8, "Deputado Distrital", "2")]
    return {
        "dg": dg, "hg": hg, "idg": str(900000 + p), "f": "s",
        "arq": [{"tp": tp, "dir": d} for tp, d in CONFIG_DIRS],
        "pl": [{
            "cd": "3220", "cdpr": "1219", "c": "ele2026", "dt": "04/10/2026", "dtlim": "04/10/2034",
            "e": [
                {"cd": "6257", "cdt2": "6258", "sqele": "20322002026", "nm": "Eleição Ordinária Federal - 2026 1º Turno (SIMULADO)",
                 "t": "1", "tp": "8", "abr": [{"cd": "br", "cp": [{"cd": "1", "ds": "Presidente", "tp": "1"}]}]},
                {"cd": "6259", "cdt2": "6260", "sqele": "20322002026", "nm": "Eleição Ordinária Estadual - 2026 1º Turno (SIMULADO)",
                 "t": "1", "tp": "1", "abr": [{"cd": "br", "cp": [{"cd": str(c), "ds": ds, "tp": tp} for c, ds, tp in cp_geral]}]},
            ],
        }],
    }


def municipios(sim: Simulacao, ele: int) -> dict:
    p = sim.passo()
    dg, hg = sim.carimbo(p)
    abr = []
    for uf in sorted(TODAS_ABRANGENCIAS):
        if uf == EXTERIOR and ele != 6257:
            continue
        lista = []
        for k in range(N_MUNICIPIOS):
            cod = Simulacao.codigo_municipio(uf, k)
            nome = f"{UF_NOMES[uf].upper()} (CAPITAL SIMULADA)" if k == 0 else f"{UF_NOMES[uf].upper()} - MUNICIPIO SIMULADO {k}"
            lista.append({"cd": f"{cod:05d}", "cdi": f"{1000000 + cod}", "nm": nome, "c": "s" if k == 0 else "n",
                          "z": [f"{z:04d}" for z in range(1, (3 if k == 0 else 1) + 1)]})
        abr.append({"cd": uf, "ds": UF_NOMES[uf].upper(), "mu": lista})
    return {"dg": dg, "hg": hg, "idg": str(800000 + p), "f": "s", "abr": abr}


def _cand_json(cargo: int, c: tuple, votos: int, vvc: int, seq: int, status: tuple[str, str], iniciou: bool) -> dict:
    numero, nome, urna, sigla, _partido, vice, sq = c
    txt, n9 = pct(votos, vvc)
    if cargo == 5:
        vs = [{"tp": t, "sqcand": str(sq + 5000 + i), "nm": f"{i + 1}o SUPLENTE DE {urna}", "nmu": f"{i + 1}o SUPLENTE DE {urna}", "sgp": sigla}
              for i, t in enumerate(("s1", "s2"))]
    else:
        vs = [{"tp": "v", "sqcand": str(sq + 5000), "nm": vice, "nmu": vice, "sgp": sigla}]
    cand = {"n": str(numero), "sqcand": str(sq), "nm": nome, "nmu": urna, "dt": "01/01/1970",
            "seq": str(seq), "e": status[0], "st": status[1], "vap": str(votos), "pvap": txt, "pvapn": n9, "vs": vs}
    if iniciou:  # como no TSE, a destinação do voto só aparece depois da primeira totalização
        cand["dvt"] = "Válido"
    return cand


def _situacao(cargo: int, ordem: list[int], vence_no_1o_turno: bool, final: bool) -> dict[int, tuple[str, str]]:
    """Por candidato (índice): (`e`, `st`). Só preenchido na totalização final."""
    if not final:
        return {i: ("n", "") for i in ordem}
    sit = {i: ("n", "Não eleito") for i in ordem}
    if cargo == 5:
        for i in ordem[: VAGAS[5]]:
            sit[i] = ("s", "Eleito")
    elif vence_no_1o_turno:
        sit[ordem[0]] = ("s", "Eleito")
    else:
        for i in ordem[:2]:
            sit[i] = ("s", "2º turno")
    return sit


def resultado(sim: Simulacao, ele: int, cargo: int, abr: str, mun: int | None = None) -> dict:
    """EA20 simulado para Brasil (só Presidente), UF ou município."""
    p = sim.passo()
    agg = sim.agregado(cargo, abr, mun, p)
    cands = sim.candidatos(cargo, abr)
    terminou = sim.terminou(abr, mun, p)
    final = terminou and agg.st > 0
    dg, hg = sim.carimbo(p)
    dt, ht = ("", "") if agg.st == 0 else (dg, hg)

    ordem = sorted(range(len(cands)), key=lambda i: (-agg.votos[i], i))
    lider = agg.votos[ordem[0]] / agg.vv if agg.vv else 0.0
    # eleito/2º turno só faz sentido onde o cargo é decidido: Brasil (Presidente) ou UF (Governador, Senador)
    decide = mun is None and ((cargo == 1 and abr == BRASIL) or cargo in (3, 5))
    situacao = _situacao(cargo, ordem, lider > 0.5, final and decide)

    dv = "n" if (cargo == 1 and not sim.dv_presidente) else "s"
    dados: dict = {
        "ele": str(ele), "t": "1", "f": "s", "sup": "n",
        "tpabr": "br" if abr == BRASIL else ("mu" if mun is not None else "uf"),
        "cdabr": abr if mun is None else f"{mun:05d}",
        "dg": dg, "hg": hg, "idg": str(1000000 + p), "dt": dt, "ht": ht,
        "dv": dv, "tf": "s" if final else "n", "and": _andamento(agg, terminou),
    }
    if decide and cargo in (1, 3) and not final and agg.st > 0:
        dados["md"] = ("e" if lider > 0.5 else "s") if agg.st / agg.ts >= 0.9 else "n"
    if final:
        dados["esae"], dados["mnae"] = "n", []

    votos = agg.votos if dv == "s" else [0] * len(cands)  # não liberado: votos zerados, seções e eleitorado seguem
    vb, vn = (agg.vb, agg.vn) if dv == "s" else (0, 0)
    vvc = sum(votos)

    nome_n, nome_m, nome_f = NOMES_CARGO[cargo]
    iniciou = agg.st > 0

    def partido(i: int, c: tuple) -> dict:
        par = {"n": str(c[0]), "sg": c[3], "nm": c[4], "nfed": "", "tvan": str(votos[i]), "tvtn": str(votos[i]),
               "cand": [_cand_json(cargo, c, votos[i], vvc, i + 1, situacao[i], iniciou)]}
        if iniciou:
            par["dvt"] = "Válido (legenda)"
        return par

    dados["carg"] = [{
        "cd": str(cargo), "nmn": nome_n, "nmm": nome_m, "nmf": nome_f, "nv": str(VAGAS[cargo]), "fed": [],
        "agr": [{"n": str(c[0]), "nm": c[4], "tp": "i", "com": c[3], "par": [partido(i, c)]} for i, c in enumerate(cands)],
    }]
    dados["s"] = bloco_s(agg.ts, agg.st, agg.st)
    dados["e"] = bloco_e(agg.te, agg.est, agg.c)
    dados["v"] = bloco_v(vvc, vb, vn)
    return dados


def _estados_municipios(sim: Simulacao, uf: str, p: int) -> tuple[int, int, int]:
    """(não iniciados, em andamento, finalizados) entre os municípios da UF."""
    nr = pt = fim = 0
    for k in range(N_MUNICIPIOS):
        st = sim.municipio(1, uf, k, p).st
        if sim.progresso_mun(uf, k, p) >= 1.0:
            fim += 1
        elif st > 0:
            pt += 1
        else:
            nr += 1
    return nr, pt, fim


def _abr_uf(sim: Simulacao, uf: str, p: int) -> dict:
    agg = sim.agregado(1, uf, None, p)  # as seções são as mesmas para todos os cargos da eleição geral
    dg, hg = sim.carimbo(p)
    nr, pt, fim = _estados_municipios(sim, uf, p)
    item: dict = {"and": _andamento(agg, sim.terminou(uf, None, p)), "tpabr": "uf", "cdabr": uf,
                  "dt": "" if agg.st == 0 else dg, "ht": "" if agg.st == 0 else hg}
    for chave, valor in (("munnr", nr), ("munpt", pt), ("munf", fim)):
        item[chave] = str(valor)
        _par(item, "p" + chave, valor, N_MUNICIPIOS)
    item["s"], item["e"] = bloco_s(agg.ts, agg.st, agg.st), bloco_e(agg.te, agg.est, agg.c)
    return item


def acompanhamento(sim: Simulacao, ele: int, uf: str = BRASIL) -> dict:
    """EA14 (uf='br'): Brasil + cada UF. EA15 (uma UF): a UF + seus municípios."""
    p = sim.passo()
    dg, hg = sim.carimbo(p)
    ufs = [u for u in TODAS_ABRANGENCIAS if ele == 6257 or u != EXTERIOR]
    abrangencias = []
    if uf == BRASIL:
        total = Agg()
        for u in ufs:
            total.somar(sim.agregado(1, u, None, p))
        iniciadas = [sim.agregado(1, u, None, p).st > 0 for u in ufs]
        finais = [sim.terminou(u, None, p) for u in ufs]
        nr, fim = iniciadas.count(False), finais.count(True)
        pt = len(ufs) - nr - fim
        item: dict = {"and": _andamento(total, all(finais)), "tpabr": "br", "cdabr": "br",
                      "dt": "" if total.st == 0 else dg, "ht": "" if total.st == 0 else hg}
        for chave, valor in (("ufsnr", nr), ("ufspt", pt), ("ufsf", fim)):
            item[chave] = str(valor)
            _par(item, "p" + chave, valor, len(ufs))
        item["s"], item["e"] = bloco_s(total.ts, total.st, total.st), bloco_e(total.te, total.est, total.c)
        abrangencias.append(item)
        abrangencias.extend(_abr_uf(sim, u, p) for u in ufs)
    else:
        abrangencias.append(_abr_uf(sim, uf, p))
        for k in range(N_MUNICIPIOS):
            m = sim.municipio(1, uf, k, p)
            abrangencias.append({
                "and": _andamento(m, sim.progresso_mun(uf, k, p) >= 1.0), "tpabr": "mun",
                "cdabr": f"{Simulacao.codigo_municipio(uf, k):05d}",
                "dt": "" if m.st == 0 else dg, "ht": "" if m.st == 0 else hg,
                "s": bloco_s(m.ts, m.st, m.st), "e": bloco_e(m.te, m.est, m.c),
            })
    return {"ele": str(ele), "t": "1", "f": "s", "dg": dg, "hg": hg, "idg": str(700000 + p), "abr": abrangencias}
