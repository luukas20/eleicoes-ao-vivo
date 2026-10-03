"""Montagem das URLs do feed de divulgação do TSE.

Estrutura (ref/tse-instrucoes-para-download-...pdf e os EA10/EA11/EA12/EA14/EA15/EA20):

    <base>/<ambiente>/<ciclo>/<eleicao>/{config|dados|fotos}/<br|zz|uf>/<arquivo>

Os diretórios vêm do EA11 (`arq[].dir`, com tokens `<...>`); os nomes de arquivo seguem os
padrões abaixo, com códigos preenchidos com zeros à esquerda. Toda entrada é validada, pois
parte dela vem de parâmetros de rota da nossa API.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from .dominio import BRASIL, EXTERIOR, UFS

# Diretórios observados no EA11 de 02/10/2026; valem até a configuração real ser carregada.
DIRS_PADRAO: dict[str, str] = {
    "ft": "<base>/<ambiente>/<ciclo>/<cd_eleicao>/fotos/<uf>",
    "cm": "<base>/<ambiente>/<ciclo>/<cd_eleicao>/config",
    "e": "<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>",
    "cs": "<base>/<ambiente>/<ciclo>/arquivo-urna/<cd_pleito>/config/<uf>",
    "ab": "<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>",
    "u": "<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>",
    "aux": "<base>/<ambiente>/<ciclo>/arquivo-urna/<cd_pleito>/dados/<uf>/<municipio>/<zona>/<secao>",
}

_TOKEN = re.compile(r"<(\w+)>")
_NUMERO = re.compile(r"\d{1,15}")


def _num(valor: object, largura: int, nome: str) -> str:
    """Número inteiro sem sinal, preenchido com zeros à esquerda até `largura`."""
    texto = str(valor).strip()
    if not _NUMERO.fullmatch(texto):
        raise ValueError(f"{nome} inválido: {valor!r}")
    numero = int(texto)
    if len(str(numero)) > largura:
        raise ValueError(f"{nome} excede {largura} dígitos: {valor!r}")
    return f"{numero:0{largura}d}"


def _id(valor: object, nome: str, maximo: int = 20) -> str:
    """Identificador numérico que NÃO recebe zeros à esquerda (ex.: `sqcand`)."""
    texto = str(valor).strip()
    if not re.fullmatch(rf"\d{{1,{maximo}}}", texto):
        raise ValueError(f"{nome} inválido: {valor!r}")
    return texto


def _uf(valor: object, *, aceita_br: bool = False) -> str:
    texto = str(valor).strip().lower()
    if texto in UFS or texto == EXTERIOR or (aceita_br and texto == BRASIL):
        return texto
    raise ValueError(f"UF inválida: {valor!r}")


class TseUrls:
    """Monta URLs a partir dos diretórios informados pelo EA11."""

    def __init__(self, base: str, ambiente: str, ciclo: str, dirs: Mapping[str, str] | None = None):
        self.base = base.rstrip("/")
        self.ambiente = ambiente
        self.ciclo = ciclo
        self._dirs = dict(DIRS_PADRAO)
        if dirs:
            self._dirs.update(dirs)

    def _dir(self, tp: str, **tokens: object) -> str:
        valores = {"base": self.base, "ambiente": self.ambiente, "ciclo": self.ciclo, **tokens}

        def troca(m: re.Match[str]) -> str:
            try:
                return str(valores[m.group(1)])
            except KeyError:
                raise KeyError(f"token <{m.group(1)}> sem valor no diretório '{tp}'") from None

        return _TOKEN.sub(troca, self._dirs[tp]).rstrip("/")

    # ---- configuração -------------------------------------------------------------------
    def config_eleicoes(self) -> str:
        """EA11: `ele-c.json`, na pasta `comum` do ambiente (independe de ciclo e eleição)."""
        return f"{self.base}/{self.ambiente}/comum/config/ele-c.json"

    def municipios(self, ele: object) -> str:
        """EA12: `mun-e<ELEICA>-cm.json`."""
        return f"{self._dir('cm', cd_eleicao=int(_num(ele, 6, 'eleição')))}/mun-e{_num(ele, 6, 'eleição')}-cm.json"

    def config_secoes(self, pleito: object, uf: object) -> str:
        """EA16: `<uf>-p<PLEITO>-cs.json`."""
        uf = _uf(uf)
        return f"{self._dir('cs', cd_pleito=int(_num(pleito, 6, 'pleito')), uf=uf)}/{uf}-p{_num(pleito, 6, 'pleito')}-cs.json"

    def auxiliar_secao(self, pleito: object, uf: object, municipio: object, zona: object, secao: object) -> str:
        """EA18: `p<PLEITO>-<uf>-m<MUNIC>-z<ZONA>-s<SECA>-aux.json`."""
        uf = _uf(uf)
        p6, m5 = _num(pleito, 6, "pleito"), _num(municipio, 5, "município")
        z4, s4 = _num(zona, 4, "zona"), _num(secao, 4, "seção")
        pasta = self._dir("aux", cd_pleito=int(p6), uf=uf, municipio=m5, zona=z4, secao=s4)
        return f"{pasta}/p{p6}-{uf}-m{m5}-z{z4}-s{s4}-aux.json"

    # ---- resultados ---------------------------------------------------------------------
    def resultado(self, ele: object, cargo: object, uf: object, municipio: object = None, zona: object = None) -> str:
        """EA20 (resultado unificado) para Brasil, UF, município ou zona.

        `uf='br'` só vale sem município. Exemplos de nome: `br-c0001-e006257-u.json`,
        `sp-c0003-e006259-u.json`, `sp71072-c0001-e006257-u.json`.
        """
        e6, c4 = _num(ele, 6, "eleição"), _num(cargo, 4, "cargo")
        uf = _uf(uf, aceita_br=True)
        if municipio is None:
            if zona is not None:
                raise ValueError("zona exige município")
            nome = f"{uf}-c{c4}-e{e6}-u.json"
        else:
            if uf == BRASIL:
                raise ValueError("município exige UF")
            m5 = _num(municipio, 5, "município")
            if zona is None:
                nome = f"{uf}{m5}-c{c4}-e{e6}-u.json"
            else:
                nome = f"{uf}{m5}-z{_num(zona, 4, 'zona')}-c{c4}-e{e6}-u.json"
        return f"{self._dir('u', cd_eleicao=int(e6), uf=uf)}/{nome}"

    def acompanhamento(self, ele: object, uf: object = BRASIL) -> str:
        """EA14 (`br-e<ELEICA>-ab.json`) para o Brasil ou EA15 (`<uf>-e<ELEICA>-ab.json`) para uma UF."""
        e6, uf = _num(ele, 6, "eleição"), _uf(uf, aceita_br=True)
        return f"{self._dir('ab', cd_eleicao=int(e6), uf=uf)}/{uf}-e{e6}-ab.json"

    def eleitos(self, ele: object, cargo: object, uf: object = BRASIL) -> str:
        """EA10: `<br|uf>-c<CARGO>-e<ELEICA>-e.json`."""
        e6, c4, uf = _num(ele, 6, "eleição"), _num(cargo, 4, "cargo"), _uf(uf, aceita_br=True)
        return f"{self._dir('e', cd_eleicao=int(e6), uf=uf)}/{uf}-c{c4}-e{e6}-e.json"

    def foto(self, ele: object, escopo: object, sqcand: object) -> str:
        """Foto do candidato: `<sqcand>.jpeg` na pasta `fotos/<br|uf>` da eleição."""
        e6, escopo = _num(ele, 6, "eleição"), _uf(escopo, aceita_br=True)
        return f"{self._dir('ft', cd_eleicao=int(e6), uf=escopo)}/{_id(sqcand, 'sqcand')}.jpeg"


def como_jws(url: str) -> str:
    """URL do arquivo assinado (`.jws`) correspondente a um `.json`; mesmo caminho, outra extensão."""
    if not url.endswith(".json"):
        raise ValueError(f"não é um .json: {url!r}")
    return url[: -len(".json")] + ".jws"
