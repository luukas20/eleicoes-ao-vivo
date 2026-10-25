"""Eleições ao Vivo — painel não oficial da apuração (dados públicos do TSE)."""
from __future__ import annotations

from flask import Flask, g, request

from .acessos import Acessos, ignorar
from .config import Settings
from .fotos import FotoCache
from .historico import Historico
from .poller import Poller
from .servico import Servico
from .store import Store
from .tse.client import TseClient

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
)


def create_app(
    settings: Settings | None = None,
    *,
    store: Store | None = None,
    client: TseClient | None = None,
    iniciar_poller: bool | None = None,
) -> Flask:
    """Monta o app. `iniciar_poller=False` (testes) deixa o Store ser alimentado à mão."""
    settings = settings or Settings.from_env()
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.config["JSON_SORT_KEYS"] = False

    store = store or Store()
    client = client or TseClient(user_agent=settings.user_agent, max_rps=settings.max_rps, workers=settings.workers)
    poller = Poller(settings, client, store)
    servico = Servico(
        settings, store, poller=poller,
        # simulado e oficial nunca se misturam: rodar a demonstração não pode poluir a curva da apuração real
        historico=Historico(settings.data_dir / "historico" / settings.ambiente),
    )
    acessos = Acessos(settings.data_dir / "acessos" / f"{settings.ambiente}.json")
    app.extensions.update(
        settings=settings, store=store, poller=poller, servico=servico, acessos=acessos,
        fotos=FotoCache(settings.data_dir / "fotos", client),
    )

    from . import api, views

    app.register_blueprint(api.bp)
    app.register_blueprint(views.bp)

    # contagem de acessos (página de Diagnóstico); o túnel da Cloudflare marca o visitante em CF-Connecting-IP
    @app.before_request
    def acesso_abrir():
        g.acesso = None
        if ignorar(request.path):
            return
        via_link = "CF-Connecting-IP" in request.headers
        cliente = (request.headers.get("CF-Connecting-IP") or request.remote_addr or "") + "|" + request.headers.get("User-Agent", "")
        acessos.abrir(request.path, via_link, cliente)
        g.acesso = via_link

    @app.teardown_request
    def acesso_fechar(_erro):
        via_link = g.get("acesso")
        if via_link is not None:
            acessos.fechar(via_link)

    @app.after_request
    def cabecalhos_de_seguranca(resposta):
        via_link = g.get("acesso")
        if via_link is not None and resposta.status_code == 200 and resposta.mimetype == "text/html":
            acessos.pagina(via_link)  # uma visita = uma página aberta (a 404 e os dados não contam)
        resposta.headers.setdefault("Content-Security-Policy", CSP)
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("Referrer-Policy", "no-referrer")
        return resposta

    if settings.iniciar_poller if iniciar_poller is None else iniciar_poller:
        poller.iniciar()
    return app
