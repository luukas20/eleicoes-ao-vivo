"""Catálogo: quais eleições, cargos e abrangências acompanhar, derivado do EA11.

Nada de código de eleição fixo: tudo vem do `ele-c.json` (ou de `TSE_ELEICOES`). O 2º turno
entra sozinho quando o TSE o publicar na configuração.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .store import chave
from .tse.dominio import BRASIL, CARGOS, CARGOS_GERAIS, Cargo, ufs_do_cargo
from .tse.urls import TseUrls

TIPOS_ACOMPANHADOS = (1, 8)  # EA11 'tp': 1 = estadual ordinária, 8 = federal ordinária


@dataclass(frozen=True)
class Disputa:
    """Um cargo numa eleição (e turno) do EA11."""

    ele: str
    turno: int
    ciclo: str
    pleito: str
    data: str | None
    cargo: Cargo
    ufs: tuple[str, ...]  # abrangências com arquivo próprio ('zz' = exterior, só no Presidente)
    nacional: bool  # existe arquivo BR (apenas Presidente)
    ele_segundo_turno: str | None = None


@dataclass(frozen=True)
class Alvo:
    """Definição estática de um arquivo a consultar periodicamente."""

    chave: str
    tipo: str  # cfg | cm | ab | u | e
    url: str
    camada: str  # nome da camada de polling (ver poller.CAMADAS)
    meta: dict


def disputas_ativas(config: dict, *, so: tuple[str, ...] = (), cargos: tuple[int, ...] = CARGOS_GERAIS) -> list[Disputa]:
    """Disputas a acompanhar: as eleições gerais do ciclo mais recente (ou as listadas em `so`),
    restritas aos `cargos` pedidos."""
    pleitos = config.get("pleitos", [])
    if so:
        elegiveis = [(p, e) for p in pleitos for e in p["eleicoes"] if e["cd"] in so]
    else:
        ciclo = max((p["ciclo"] for p in pleitos), default="")
        elegiveis = [
            (p, e) for p in pleitos if p["ciclo"] == ciclo for e in p["eleicoes"] if e["tipo"] in TIPOS_ACOMPANHADOS
        ]

    disputas: list[Disputa] = []
    for pleito, eleicao in elegiveis:
        for abr in eleicao["abrangencias"]:
            for c in abr["cargos"]:
                cargo = CARGOS.get(c["cd"])
                if cargo is None or cargo.cd not in CARGOS_GERAIS or cargo.cd not in cargos:
                    continue  # ex.: Conselheiro Distrital (25) está fora do escopo
                nacional_ou_todas = abr["cd"] == BRASIL
                disputas.append(
                    Disputa(
                        ele=eleicao["cd"],
                        turno=eleicao["turno"],
                        ciclo=pleito["ciclo"],
                        pleito=pleito["cd"],
                        data=pleito["data"],
                        cargo=cargo,
                        ufs=ufs_do_cargo(cargo.cd) if nacional_ou_todas else (abr["cd"],),
                        nacional=cargo.cd == 1 and nacional_ou_todas,
                        ele_segundo_turno=eleicao["cdt2"],
                    )
                )
    return disputas


def montar_alvos(disputas: list[Disputa], urls_do_ciclo: Callable[[str], TseUrls]) -> list[Alvo]:
    """Arquivos a consultar para as disputas: EA12/EA14 por eleição e um EA20 por cargo/abrangência."""
    alvos: dict[str, Alvo] = {}

    def add(alvo: Alvo) -> None:
        alvos.setdefault(alvo.chave, alvo)

    for d in disputas:
        urls = urls_do_ciclo(d.ciclo)
        base = {"ele": d.ele, "turno": d.turno, "cargo": d.cargo.cd}
        add(Alvo(chave("cm", d.ele), "cm", urls.municipios(d.ele), "estatico", {"ele": d.ele}))
        add(Alvo(chave("ab", d.ele, abr=BRASIL), "ab", urls.acompanhamento(d.ele, BRASIL), "nacional", {"ele": d.ele, "abr": BRASIL}))
        if d.nacional:
            add(Alvo(chave("u", d.ele, d.cargo.cd, BRASIL), "u", urls.resultado(d.ele, d.cargo.cd, BRASIL), "nacional", {**base, "abr": BRASIL}))
        camada_uf = "uf" if d.cargo.cd in (1, 3, 5) else "uf_lento"
        for uf in d.ufs:
            add(Alvo(chave("u", d.ele, d.cargo.cd, uf), "u", urls.resultado(d.ele, d.cargo.cd, uf), camada_uf, {**base, "abr": uf}))
    return list(alvos.values())
