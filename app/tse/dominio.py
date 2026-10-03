"""Constantes de domínio: UFs, cargos e quais cargos existem em cada UF (eleições gerais)."""
from __future__ import annotations

from dataclasses import dataclass

BRASIL = "br"
EXTERIOR = "zz"

UF_NOMES: dict[str, str] = {
    "ac": "Acre", "al": "Alagoas", "am": "Amazonas", "ap": "Amapá", "ba": "Bahia",
    "ce": "Ceará", "df": "Distrito Federal", "es": "Espírito Santo", "go": "Goiás",
    "ma": "Maranhão", "mg": "Minas Gerais", "ms": "Mato Grosso do Sul",
    "mt": "Mato Grosso", "pa": "Pará", "pb": "Paraíba", "pe": "Pernambuco",
    "pi": "Piauí", "pr": "Paraná", "rj": "Rio de Janeiro", "rn": "Rio Grande do Norte",
    "ro": "Rondônia", "rr": "Roraima", "rs": "Rio Grande do Sul", "sc": "Santa Catarina",
    "se": "Sergipe", "sp": "São Paulo", "to": "Tocantins",
    EXTERIOR: "Exterior",
}
UFS: tuple[str, ...] = tuple(sorted(k for k in UF_NOMES if k != EXTERIOR))


@dataclass(frozen=True)
class Cargo:
    cd: int
    slug: str
    nome: str
    tipo: str  # "majoritario" | "proporcional"


CARGOS: dict[int, Cargo] = {
    1: Cargo(1, "presidente", "Presidente", "majoritario"),
    3: Cargo(3, "governador", "Governador", "majoritario"),
    5: Cargo(5, "senador", "Senador", "majoritario"),
    6: Cargo(6, "deputado-federal", "Deputado Federal", "proporcional"),
    7: Cargo(7, "deputado-estadual", "Deputado Estadual", "proporcional"),
    8: Cargo(8, "deputado-distrital", "Deputado Distrital", "proporcional"),
    11: Cargo(11, "prefeito", "Prefeito", "majoritario"),
    13: Cargo(13, "vereador", "Vereador", "proporcional"),
}
CARGO_POR_SLUG: dict[str, Cargo] = {c.slug: c for c in CARGOS.values()}

# Cargos das eleições gerais que o painel acompanha (a ordem define a ordem de exibição).
CARGOS_GERAIS: tuple[int, ...] = (1, 3, 5, 6, 7, 8)


def ufs_do_cargo(cargo: int) -> tuple[str, ...]:
    """UFs (e exterior) onde o cargo existe numa eleição geral.

    Presidente: todas as UFs + exterior. Deputado Estadual: todas menos o DF, que elege
    Deputado Distrital. Os demais cargos existem nas 27 UFs. O exterior só vota Presidente.
    """
    if cargo == 1:
        return UFS + (EXTERIOR,)
    if cargo in (3, 5, 6):
        return UFS
    if cargo == 7:
        return tuple(u for u in UFS if u != "df")
    if cargo == 8:
        return ("df",)
    return ()


def nome_abrangencia(codigo: str) -> str:
    """Nome legível de 'br', de uma UF ou do exterior."""
    codigo = codigo.lower()
    return "Brasil" if codigo == BRASIL else UF_NOMES.get(codigo, codigo.upper())
