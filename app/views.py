"""Páginas HTML, proxy de fotos e verificação de saúde."""
from __future__ import annotations

import re

from flask import Blueprint, Response, abort, current_app, render_template, request

from .tse.dominio import UF_NOMES, UFS

bp = Blueprint("web", __name__)

REPO_URL = "https://github.com/luukas20/eleicoes-ao-vivo"
PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 75"><rect width="60" height="75" fill="#E4DFD2"/>'
    '<circle cx="30" cy="25" r="11" fill="#A9A292"/><ellipse cx="30" cy="66" rx="22" ry="29" fill="#A9A292"/></svg>'
)


def _url_base() -> str:
    """Endereço do painel como o visitante o vê (atrás de um túnel o esquema é https): para as tags de compartilhamento."""
    esquema = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
    return f"{esquema if esquema in ('http', 'https') else request.scheme}://{request.host}/"


def _contexto(pagina: str, aba: str | None = None, **extra):
    """`aba` marca o item ativo da navegação (presidente, governador, senador, deputado-federal...); None = nenhum."""
    return render_template(
        f"{pagina}.html",
        pagina=pagina,
        aba=aba,
        ufs=[(u, UF_NOMES[u]) for u in UFS],
        repo_url=REPO_URL,
        url_base=_url_base(),
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


@bp.get("/deputados-federais")
def deputados_federais():
    return _contexto("proporcional", "deputado-federal", slug="deputado-federal", titulo="Deputados Federais",
                     composicao="Câmara dos Deputados", escopo="Vagas de Deputado Federal somadas das 27 UFs.")


@bp.get("/deputados-estaduais")
def deputados_estaduais():
    return _contexto("proporcional", "deputado-estadual", slug="deputado-estadual", titulo="Deputados Estaduais",
                     composicao="Assembleias Legislativas",
                     escopo="Vagas das 26 assembleias legislativas e da Câmara Legislativa do DF (onde o cargo se chama Deputado Distrital), somadas.")


@bp.get("/status")
def status():
    return _contexto("status")


@bp.get("/healthz")
def healthz():
    return {"ok": True}


@bp.app_errorhandler(404)
def nao_encontrada(_erro):
    """Página de erro com a cara do painel; API, fotos e arquivos estáticos seguem com a resposta enxuta."""
    if request.path.startswith(("/api/", "/foto/", "/static/")) or not request.accept_mimetypes.accept_html:
        return Response("não encontrado", status=404, mimetype="text/plain")
    pagina = _contexto("erro", codigo=404, titulo="Página não encontrada",
                       texto="O endereço não existe neste painel. Volte ao início ou escolha uma UF no menu.")
    return Response(pagina, status=404, mimetype="text/html")


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
