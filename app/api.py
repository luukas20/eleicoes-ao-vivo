"""API JSON (somente leitura) que alimenta a interface.

Os endpoints de dados usam ETag: entre uma totalização e outra o navegador recebe 304. O que muda
a cada segundo (idade da última confirmação junto ao TSE) viaja nos cabeçalhos `X-Defasagem-S`,
`X-Desatualizado` e `X-Disjuntor`, que também chegam nas respostas 304.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from flask import Blueprint, Response, current_app, request

from .servico import Servico

bp = Blueprint("api", __name__, url_prefix="/api/v1")

CARGOS_TABELA = ("governador", "senador")


def servico() -> Servico:
    return current_app.extensions["servico"]


def _com_frescor(resposta: Response) -> Response:
    f = servico().frescor()
    resposta.headers["X-Defasagem-S"] = "" if f["defasagem_s"] is None else str(f["defasagem_s"])
    resposta.headers["X-Desatualizado"] = "1" if f["desatualizado"] else "0"
    resposta.headers["X-Disjuntor"] = "1" if f["disjuntor"]["aberto"] else "0"
    return resposta


def responder(payload: Any, status: int = 200, *, etag: bool = True) -> Response:
    corpo = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tag = '"' + hashlib.md5(corpo).hexdigest() + '"'
    if etag and status == 200 and request.headers.get("If-None-Match") == tag:
        resposta = Response(status=304)
    else:
        resposta = Response(corpo, status=status, mimetype="application/json")
    if etag and status == 200:
        resposta.headers["ETag"] = tag
    resposta.headers["Cache-Control"] = "no-cache"
    return _com_frescor(resposta)


def erro(mensagem: str, status: int) -> Response:
    return responder({"erro": mensagem}, status, etag=False)


def _turno() -> tuple[int | None, Response | None]:
    bruto = request.args.get("turno")
    if bruto is None:
        return None, None
    if bruto not in ("1", "2"):
        return None, erro("turno deve ser 1 ou 2", 400)
    return int(bruto), None


@bp.get("/meta")
def meta():
    return responder(servico().meta(), etag=False)


@bp.get("/presidente")
def presidente():
    turno, falha = _turno()
    if falha:
        return falha
    dados = servico().painel_presidente(turno)
    return responder(dados) if dados else erro("eleição presidencial não encontrada (aguardando o arquivo de configuração do TSE?)", 404)


@bp.get("/cargo/<slug>")
def cargo(slug: str):
    if slug not in CARGOS_TABELA:
        return erro("cargo desconhecido", 404)
    turno, falha = _turno()
    if falha:
        return falha
    dados = servico().tabela_cargo(slug, turno)
    return responder(dados) if dados else erro("eleição não encontrada para este cargo/turno", 404)


@bp.get("/uf/<uf>")
def uf(uf: str):
    turno, falha = _turno()
    if falha:
        return falha
    dados = servico().pagina_uf(uf, turno)
    return responder(dados) if dados else erro("UF desconhecida", 404)


@bp.get("/status")
def status():
    s = servico()
    poller = current_app.extensions["poller"]
    return responder(
        {
            "frescor": s.frescor(),
            "poller": poller.estado(),
            "armazenamento": {"arquivos": len(s.store.itens()), "versao": s.store.versao},
            "eleicoes": [
                {"ele": d.ele, "turno": d.turno, "cargo": d.cargo.slug, "ufs": len(d.ufs), "ciclo": d.ciclo}
                for d in s.disputas()
            ],
        },
        etag=False,
    )
