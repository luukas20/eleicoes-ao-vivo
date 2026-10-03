"""Páginas HTML, proxy de fotos e verificação de saúde."""
from __future__ import annotations

import re

from flask import Blueprint, Response, abort, current_app, render_template

from .tse.dominio import UF_NOMES, UFS

bp = Blueprint("web", __name__)

REPO_URL = "https://github.com/luukas20/eleicoes-ao-vivo"
PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 75"><rect width="60" height="75" fill="#d6dae0"/>'
    '<circle cx="30" cy="25" r="11" fill="#969eaa"/><ellipse cx="30" cy="66" rx="22" ry="29" fill="#969eaa"/></svg>'
)


def _contexto(pagina: str, aba: str | None = None, **extra):
    """`aba` marca o item ativo da navegação (presidente, governador, senador); None = nenhum."""
    return render_template(
        f"{pagina}.html",
        pagina=pagina,
        aba=aba,
        ufs=[(u, UF_NOMES[u]) for u in UFS],
        repo_url=REPO_URL,
        **extra,
    )


@bp.get("/")
def painel():
    return _contexto("painel", "presidente")


@bp.get("/uf/<uf>")
def pagina_uf(uf: str):
    uf = uf.lower()
    if uf not in UF_NOMES or uf == "zz":
        abort(404)
    return _contexto("uf", uf=uf, nome_uf=UF_NOMES[uf])


@bp.get("/municipio/<uf>/<codigo>")
def pagina_municipio(uf: str, codigo: str):
    uf = uf.lower()
    if uf not in UF_NOMES or uf == "zz" or not re.fullmatch(r"\d{1,5}", codigo):
        abort(404)
    return _contexto("municipio", uf=uf, nome_uf=UF_NOMES[uf], codigo=codigo.zfill(5))


@bp.get("/governadores")
def governadores():
    return _contexto("cargo", "governador", slug="governador", titulo="Governadores")


@bp.get("/senadores")
def senadores():
    return _contexto("cargo", "senador", slug="senador", titulo="Senadores")


@bp.get("/status")
def status():
    return _contexto("status")


@bp.get("/healthz")
def healthz():
    return {"ok": True}


def _placeholder() -> Response:
    resposta = Response(PLACEHOLDER_SVG, mimetype="image/svg+xml")
    resposta.headers["Cache-Control"] = "public, max-age=300"
    return resposta


@bp.get("/foto/<int:ele>/<escopo>/<sq>")
def foto(ele: int, escopo: str, sq: str):
    """Foto do candidato, buscada no TSE uma única vez e guardada em disco."""
    servico = current_app.extensions["servico"]
    if not (sq.isdigit() and len(sq) <= 20) or (escopo != "br" and escopo not in UF_NOMES):
        abort(404)
    if not servico.foto_valida(ele, escopo, sq):  # só candidatos que aparecem nos arquivos do TSE
        return _placeholder()
    urls = servico.urls(ele)
    if urls is None:
        return _placeholder()
    dados = current_app.extensions["fotos"].obter(ele, escopo, sq, urls.foto(ele, escopo, sq))
    if dados is None:
        return _placeholder()
    resposta = Response(dados, mimetype="image/jpeg")
    resposta.headers["Cache-Control"] = "public, max-age=86400"
    return resposta
