"""Eleições ao Vivo — painel não oficial da apuração (dados públicos do TSE)."""
from __future__ import annotations

from flask import Flask

from .config import Settings
from .cores import Cores
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
        cores=Cores(settings.data_dir / "cores.json"),
        historico=Historico(settings.data_dir / "historico" / settings.ambiente),  # simulado e oficial nunca se misturam
    )
    app.extensions.update(
        settings=settings, store=store, poller=poller, servico=servico,
        fotos=FotoCache(settings.data_dir / "fotos", client),
    )

    from . import api, views

    app.register_blueprint(api.bp)
    app.register_blueprint(views.bp)

    @app.after_request
    def cabecalhos_de_seguranca(resposta):
        resposta.headers.setdefault("Content-Security-Policy", CSP)
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("Referrer-Policy", "no-referrer")
        return resposta

    if settings.iniciar_poller if iniciar_poller is None else iniciar_poller:
        poller.iniciar()
    return app
