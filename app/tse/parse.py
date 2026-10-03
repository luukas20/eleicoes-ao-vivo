"""Interpretação dos arquivos JSON do TSE (EA11, EA12, EA14/EA15, EA20, EA10).

Os arquivos trazem todos os valores como texto (`"158745502"`, `"45,32"`). Aqui eles viram um
modelo enxuto para a nossa API, **sem alterar o conteúdo publicado**:

* contadores viram `int`;
* percentuais viram `{"t": <texto como publicado>, "n": <float>}` — `t` é o que se exibe
  (ex.: `"45,32"`); `n` vem do campo de 9 casas do TSE (quando existe) e serve para ordenar e
  dimensionar barras. Nunca recalculamos percentuais (o TSE arredonda half-up).

Horários `dg/hg/dt/ht` estão em horário de Brasília e saem em ISO 8601 com fuso.
"""
from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")

# Percentuais: chave com 2 casas -> chave gêmea numérica de 9 casas (EA14, EA15, EA20).
S_PARES = {"pst": "pstn", "psnt": "psntn", "psi": "psin", "psni": "psnin", "psa": "psan", "psna": "psnan"}
E_PARES = {
    "pest": "pestn", "pesnt": "pesntn", "pesi": "pesin", "pesni": "pesnin",
    "pesa": "pesan", "pesna": "pesnan", "pc": "pcn", "pa": "pan",
}
V_PARES = {
    "pvvc": "pvvcn", "pvv": "pvvn", "pvl": "pvln", "pvnom": "pvnomn", "pvan": "pvann",
    "pvansj": "pvansjn", "pvb": "pvbn", "ptvn": "ptvnn", "pvn": "pvnn", "pvnt": "pvntn",
}
ABR_PARES = {
    "pufsnr": "pufsnrn", "pufspt": "pufsptn", "pufsf": "pufsfn",
    "pmunnr": "pmunnrn", "pmunpt": "pmunptn", "pmunf": "pmunfn",
}


# ---- utilitários ----------------------------------------------------------------------------
def decodificar(corpo: bytes | str) -> dict[str, Any]:
    """JSON do TSE (UTF-8, às vezes com BOM) -> dict."""
    texto = corpo.decode("utf-8-sig") if isinstance(corpo, (bytes, bytearray)) else corpo
    dados = json.loads(texto)
    if not isinstance(dados, dict):
        raise ValueError("JSON do TSE deveria ser um objeto")
    return dados


def to_int(valor: Any, padrao: int = 0) -> int:
    """`"123"` -> 123; vazio/inválido -> `padrao`."""
    if valor is None or isinstance(valor, bool):
        return padrao
    if isinstance(valor, int):
        return valor
    texto = str(valor).strip()
    if not texto:
        return padrao
    try:
        return int(texto)
    except ValueError:
        try:
            return int(float(texto.replace(",", ".")))
        except ValueError:
            return padrao


def to_float(valor: Any, padrao: float = 0.0) -> float:
    """Aceita `"45,32"`, `"45.321234567"`, `"1.234,5"` e números; vazio/inválido -> `padrao`."""
    if valor is None or isinstance(valor, bool):
        return padrao
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return padrao
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")  # "1.234,5" -> "1234.5"
    elif texto.count(".") > 1:
        texto = texto.replace(".", "")  # "1.234.567" (milhar) -> "1234567"
    try:
        return float(texto)
    except ValueError:
        return padrao


def parse_data_hora(data: Any, hora: Any) -> datetime | None:
    """`"02/10/2026"`, `"20:13:54"` (horário de Brasília) -> datetime com fuso; vazio -> None."""
    if not data or not hora:
        return None
    try:
        return datetime.strptime(f"{data} {hora}", "%d/%m/%Y %H:%M:%S").replace(tzinfo=BRT)
    except ValueError:
        return None


def parse_data(data: Any) -> str | None:
    """`"04/10/2026"` -> `"2026-10-04"`."""
    try:
        return datetime.strptime(str(data), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def iso(momento: datetime | None) -> str | None:
    return momento.isoformat() if momento else None


def sem_acentos(texto: str) -> str:
    """Minúsculas e sem acentos, para busca."""
    base = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in base if not unicodedata.combining(c)).casefold()


def normalizar_bloco(bruto: dict[str, Any] | None, pares: dict[str, str]) -> dict[str, Any]:
    """Bloco `s`, `e` ou `v`: contadores viram int; percentuais viram `{"t", "n"}`."""
    bruto = bruto or {}
    gemeos = set(pares.values())
    saida: dict[str, Any] = {}
    for chave, valor in bruto.items():
        if chave in gemeos:
            continue
        if chave in pares:
            saida[chave] = {"t": "" if valor is None else str(valor), "n": to_float(bruto.get(pares[chave], valor))}
        else:
            saida[chave] = to_int(valor)
    return saida


def _cabecalho(dados: dict[str, Any]) -> dict[str, Any]:
    return {
        "ele": str(dados.get("ele", "")),
        "turno": to_int(dados.get("t"), 1),
        "fase": dados.get("f", ""),
        "idg": str(dados.get("idg", "")),
        "gerado_em": iso(parse_data_hora(dados.get("dg"), dados.get("hg"))),
    }


# ---- EA11: configuração de eleições -----------------------------------------------------------
def parse_config_eleicoes(dados: dict[str, Any]) -> dict[str, Any]:
    pleitos = []
    for pl in dados.get("pl", []) or []:
        eleicoes = []
        for e in pl.get("e", []) or []:
            abrangencias = [
                {
                    "cd": str(a.get("cd", "")).lower(),
                    "cargos": [
                        {"cd": to_int(c.get("cd")), "nome": c.get("ds", ""), "tipo": to_int(c.get("tp"))}
                        for c in a.get("cp", []) or []
                    ],
                    "municipios": [{"cd": str(m.get("cd", "")), "cdi": str(m.get("cdi", ""))} for m in a.get("mu", []) or []],
                }
                for a in e.get("abr", []) or []
            ]
            eleicoes.append(
                {
                    "cd": str(e.get("cd", "")),
                    "cdt2": str(e.get("cdt2", "")) or None,
                    "sqele": str(e.get("sqele", "")),
                    "nome": e.get("nm", ""),
                    "turno": to_int(e.get("t"), 1),
                    "tipo": to_int(e.get("tp")),
                    "abrangencias": abrangencias,
                }
            )
        pleitos.append(
            {
                "cd": str(pl.get("cd", "")),
                "cdpr": str(pl.get("cdpr", "")),
                "ciclo": pl.get("c", ""),
                "data": parse_data(pl.get("dt")),
                "limite": parse_data(pl.get("dtlim")),
                "eleicoes": eleicoes,
            }
        )
    return {
        "idg": str(dados.get("idg", "")),
        "gerado_em": iso(parse_data_hora(dados.get("dg"), dados.get("hg"))),
        "fase": dados.get("f", ""),
        "dirs": {a.get("tp", ""): a.get("dir", "") for a in dados.get("arq", []) or [] if a.get("tp")},
        "pleitos": pleitos,
    }


# ---- EA12: configuração de municípios ----------------------------------------------------------
def parse_municipios(dados: dict[str, Any]) -> dict[str, Any]:
    ufs: dict[str, Any] = {}
    for a in dados.get("abr", []) or []:
        municipios = [
            {
                "cd": str(m.get("cd", "")),
                "cdi": str(m.get("cdi", "")),
                "nome": m.get("nm", ""),
                "capital": m.get("c") == "s",
                "zonas": list(m.get("z", []) or []),
                "busca": sem_acentos(m.get("nm", "")),
            }
            for m in a.get("mu", []) or []
        ]
        ufs[str(a.get("cd", "")).lower()] = {"nome": a.get("ds", ""), "municipios": municipios}
    return {
        "idg": str(dados.get("idg", "")),
        "gerado_em": iso(parse_data_hora(dados.get("dg"), dados.get("hg"))),
        "fase": dados.get("f", ""),
        "ufs": ufs,
    }


# ---- EA14 / EA15: acompanhamento --------------------------------------------------------------
def parse_acompanhamento(dados: dict[str, Any]) -> dict[str, Any]:
    abrangencias = []
    for a in dados.get("abr", []) or []:
        resto = {k: v for k, v in a.items() if k not in ("and", "tpabr", "cdabr", "dt", "ht", "s", "e")}
        abrangencias.append(
            {
                "tipo": a.get("tpabr", ""),
                "codigo": str(a.get("cdabr", "")).lower(),
                "andamento": a.get("and", ""),
                "atualizado_em": iso(parse_data_hora(a.get("dt"), a.get("ht"))),
                "secoes": normalizar_bloco(a.get("s"), S_PARES),
                "eleitorado": normalizar_bloco(a.get("e"), E_PARES),
                "contagem": normalizar_bloco(resto, ABR_PARES),
            }
        )
    return {**_cabecalho(dados), "abrangencias": abrangencias}


# ---- EA20: resultado unificado -----------------------------------------------------------------
def _achatar_candidatos(carg: dict[str, Any]) -> list[dict[str, Any]]:
    """`carg.agr[].par[].cand[]` -> lista plana, ordenada por votos (empate: ordem na urna)."""
    candidatos = []
    for agr in carg.get("agr", []) or []:
        for par in agr.get("par", []) or []:
            for c in par.get("cand", []) or []:
                vs = c.get("vs", []) or []
                vices = [v for v in vs if v.get("tp") == "v"]
                suplentes = [v for v in vs if v.get("tp") in ("s1", "s2")]
                candidatos.append(
                    {
                        "sq": str(c.get("sqcand", "")),
                        "numero": str(c.get("n", "")),
                        "nome": c.get("nm", ""),
                        "urna": c.get("nmu") or c.get("nm", ""),
                        "partido": par.get("sg", ""),
                        "partido_nome": par.get("nm", ""),
                        "agremiacao": agr.get("nm", ""),
                        "agremiacao_tipo": agr.get("tp", ""),
                        "composicao": agr.get("com", ""),
                        "votos": to_int(c.get("vap")),
                        "pct": {"t": str(c.get("pvap", "")), "n": to_float(c.get("pvapn", c.get("pvap")))},
                        "eleito": c.get("e") == "s",
                        "situacao": c.get("st", ""),
                        "seq": to_int(c.get("seq")),
                        "vice": (vices[0].get("nmu") or vices[0].get("nm")) if vices else None,
                        "suplentes": [s.get("nmu") or s.get("nm") for s in suplentes],
                    }
                )
    candidatos.sort(key=lambda c: (-c["votos"], c["seq"], c["nome"]))
    return candidatos


def _agremiacoes(carg: dict[str, Any]) -> list[dict[str, Any]]:
    """Cargos proporcionais: totais por partido/federação e vagas."""
    saida = []
    for agr in carg.get("agr", []) or []:
        partidos = [
            {
                "n": str(p.get("n", "")),
                "sigla": p.get("sg", ""),
                "nome": p.get("nm", ""),
                "votos_nominais": to_int(p.get("tvtn")),
                "votos_legenda": to_int(p.get("tvtl")),
            }
            for p in agr.get("par", []) or []
        ]
        nominais = to_int(agr["tvtn"]) if "tvtn" in agr else sum(p["votos_nominais"] for p in partidos)
        legenda = to_int(agr["tvtl"]) if "tvtl" in agr else sum(p["votos_legenda"] for p in partidos)
        saida.append(
            {
                "n": str(agr.get("n", "")),
                "nome": agr.get("nm", ""),
                "tipo": agr.get("tp", ""),
                "composicao": agr.get("com", ""),
                "vagas": to_int(agr.get("vag")),
                "votos_nominais": nominais,
                "votos_legenda": legenda,
                "votos_total": nominais + legenda,
                "partidos": partidos,
            }
        )
    saida.sort(key=lambda a: (-a["votos_total"], a["nome"]))
    return saida


def parse_resultado(dados: dict[str, Any]) -> dict[str, Any]:
    """EA20 (BR, UF, município ou zona) -> modelo da API. Ver docstring do módulo."""
    carg = (dados.get("carg") or [None])[0]
    cargo = None
    candidatos: list[dict[str, Any]] = []
    agremiacoes: list[dict[str, Any]] = []
    if carg:
        cargo = {
            "cd": to_int(carg.get("cd")),
            "nome": carg.get("nmn", ""),
            "nome_masculino": carg.get("nmm", ""),
            "nome_feminino": carg.get("nmf", ""),
            "vagas": to_int(carg.get("nv")),
            "quociente_eleitoral": to_int(carg["qe"]) if "qe" in carg else None,
        }
        candidatos = _achatar_candidatos(carg)
        if "qe" in carg or any("vag" in a for a in carg.get("agr", []) or []):
            agremiacoes = _agremiacoes(carg)
    return {
        **_cabecalho(dados),
        "abrangencia": {"tipo": dados.get("tpabr", ""), "codigo": str(dados.get("cdabr", "")).lower()},
        "totalizado_em": iso(parse_data_hora(dados.get("dt"), dados.get("ht"))),
        "estado": {
            "divulga": dados.get("dv", "s") != "n",
            "andamento": dados.get("and", ""),
            "totalizacao_final": dados.get("tf") == "s",
            "definido": dados.get("md") or None,  # 'e' eleito | 's' 2º turno | 'n' não definido
            "sem_eleito": dados.get("esae") == "s",
            "motivos": list(dados.get("mnae", []) or []),
            "suplementar": dados.get("sup") == "s",
        },
        "cargo": cargo,
        "secoes": normalizar_bloco(dados.get("s"), S_PARES),
        "eleitorado": normalizar_bloco(dados.get("e"), E_PARES),
        "votos": normalizar_bloco(dados.get("v"), V_PARES),
        "candidatos": candidatos,
        "agremiacoes": agremiacoes,
    }


# ---- EA10: eleitos -----------------------------------------------------------------------------
def parse_eleitos(dados: dict[str, Any]) -> dict[str, Any]:
    abrangencias = []
    for a in dados.get("abr", []) or []:
        eleitos = []
        for c in a.get("cand", []) or []:
            vs = c.get("vs", []) or []
            vices = [v for v in vs if v.get("tp") == "v"]
            eleitos.append(
                {
                    "sq": str(c.get("sqcand", "")),
                    "numero": str(c.get("n", "")),
                    "nome": c.get("nm", ""),
                    "urna": c.get("nmu") or c.get("nm", ""),
                    "partido": c.get("sgp", ""),
                    "composicao": c.get("com", ""),
                    "votos": to_int(c.get("vap")),
                    "seq": to_int(c.get("seq")),
                    "vice": (vices[0].get("nmu") or vices[0].get("nm")) if vices else None,
                    "suplentes": [(v.get("nmu") or v.get("nm")) for v in vs if v.get("tp") in ("s1", "s2")],
                }
            )
        abrangencias.append(
            {
                "tipo": a.get("tpabr", ""),
                "codigo": str(a.get("cdabr", "")).lower(),
                "nome": a.get("nmabr", ""),
                "atualizado_em": iso(parse_data_hora(a.get("dt"), a.get("ht"))),
                "votos_computados": to_int(a.get("tvap")),
                "sem_candidato": a.get("scv") == "s",
                "sem_eleito": a.get("esae") == "s",
                "motivos": list(a.get("mnae", []) or []),
                "eleitos": eleitos,
            }
        )
    return {
        **_cabecalho(dados),
        "cargo": {"cd": to_int(dados.get("cdcar")), "nome": dados.get("nmcar", "")},
        "abrangencia": {"codigo": str(dados.get("cdabr", "")).lower(), "nome": dados.get("nmabr", "")},
        "abrangencias": abrangencias,
    }
