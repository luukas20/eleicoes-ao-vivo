"""Atribuição das cores dos partidos aos candidatos de uma disputa.

A cor de um candidato é a do seu partido: não depende de votos nem de posição, então nunca "pula" durante a
apuração. O único cuidado é quando dois candidatos da mesma disputa teriam cores parecidas (PT e PSTU, dois
tons de azul...): quem tem prioridade (`partidos.PRIORIDADE`) fica com a cor do partido, e o outro recebe a
variante alternativa do próprio partido ou, se também estiver ocupada, uma cor de reserva. A escolha só
depende de quais siglas disputam o cargo — fixo desde o registro das candidaturas —, então é estável durante
a noite e igual em todas as UFs (no Presidente, a lista de candidatos é a mesma em todo lugar).
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Iterable

from . import partidos

LIMITE_DISTINTO = 10.0  # distância mínima (OKLab ×100) entre duas cores da mesma disputa; abaixo disso troca para a variante
LIMITE_MINIMO = 5.0     # se nem a variante chega ao limite, ainda vale mais que uma cor de outra família desde que dê para notar
NEUTRO = "neutro"


def _linear(hexa: str) -> tuple[float, float, float]:
    saida = []
    for i in (1, 3, 5):
        v = int(hexa[i:i + 2], 16) / 255
        saida.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return saida[0], saida[1], saida[2]


def oklab(hexa: str) -> tuple[float, float, float]:
    r, g, b = _linear(hexa)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def distancia(a: str, b: str) -> float:
    """Diferença perceptível entre duas cores (hex), em OKLab ×100: ~2 mal se nota, ~10 é nítida, 20+ é óbvia."""
    return 100 * math.dist(oklab(a), oklab(b))


def _posicao(sigla: str) -> int:
    partido = partidos.partido_de(sigla)
    return partidos.PRIORIDADE.index(partido) if partido in partidos.PRIORIDADE else len(partidos.PRIORIDADE)


def _opcoes(sigla: str) -> tuple[list[str], list[str]]:
    """(chaves do próprio partido: cor e variante; chaves de reserva), da preferida para a última."""
    partido = partidos.partido_de(sigla)
    proprias = [partidos.chave_de(partido), partidos.chave_de(partido, alternativa=True)] if partido else []
    return proprias, [*partidos.RESERVA, NEUTRO]


def _folga(chave: str, ocupadas: dict[str, str]) -> float:
    claro = partidos.hex_claro(chave)
    return min((distancia(claro, outra) for outra in ocupadas.values()), default=math.inf)


@lru_cache(maxsize=1024)
def _atribuir(pares: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    ocupadas: dict[str, str] = {}  # chave -> cor clara, para medir a distância
    saida: dict[str, str] = {}
    for sq, sigla in sorted(pares, key=lambda p: (_posicao(p[1]), p[1], p[0])):
        proprias, reservas = _opcoes(sigla)
        proprias = [o for o in proprias if o not in ocupadas]
        reservas = [o for o in reservas if o not in ocupadas or o == NEUTRO]
        escolhida = (
            # 1. a cor do partido (ou a variante dele) se já é claramente diferente das outras da disputa
            next((o for o in proprias if _folga(o, ocupadas) >= LIMITE_DISTINTO), None)
            # 2. senão, a melhor das duas se ainda dá para notar a diferença: mantém a família de cor do partido
            or next((o for o in sorted(proprias, key=lambda o: -_folga(o, ocupadas)) if _folga(o, ocupadas) >= LIMITE_MINIMO), None)
            # 3. senão, uma cor de reserva distinta; 4. por fim, a opção mais afastada das já usadas
            or next((o for o in reservas if _folga(o, ocupadas) >= LIMITE_DISTINTO), None)
            or max(proprias + reservas, key=lambda o: _folga(o, ocupadas))
        )
        ocupadas[escolhida] = partidos.hex_claro(escolhida)
        saida[sq] = escolhida
    return tuple(saida.items())


def atribuir(candidatos: Iterable[dict]) -> dict[str, str]:
    """{sq: chave de cor} para os candidatos (dicts com `sq` e `partido`) de UMA disputa em UMA abrangência."""
    return dict(_atribuir(tuple((str(c["sq"]), str(c.get("partido") or "")) for c in candidatos)))
