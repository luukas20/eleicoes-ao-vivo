"""Inicia o painel (consulta o TSE em segundo plano e serve a interface).

    python run.py

Configuração por variáveis de ambiente (veja .env.example). Contra o simulador local:
    $env:TSE_BASE="http://127.0.0.1:5001"; $env:TSE_AMBIENTE="simulado"; $env:ESCALA_POLLING="0.25"
Para abrir o painel a outros aparelhos da rede (ex.: um telão): $env:HOST="0.0.0.0"
"""
from __future__ import annotations

import logging
import logging.handlers

from waitress import serve

from app import create_app
from app.config import Settings


def configurar_logs(settings: Settings) -> None:
    """Log no terminal e em arquivo rotativo (data/logs/painel.log), para investigar depois da apuração."""
    formato = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    terminal = logging.StreamHandler()
    terminal.setFormatter(formato)
    raiz.addHandler(terminal)
    try:
        pasta = settings.data_dir / "logs"
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = logging.handlers.RotatingFileHandler(pasta / "painel.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        arquivo.setFormatter(formato)
        raiz.addHandler(arquivo)
    except OSError:
        raiz.warning("não foi possível gravar o log em arquivo; seguindo só com o terminal")
    logging.getLogger("waitress.queue").setLevel(logging.ERROR)


def main() -> None:
    settings = Settings.from_env()
    configurar_logs(settings)
    app = create_app(settings)
    print(f"Painel em http://{settings.host}:{settings.port}  | fonte: {settings.tse_base}/{settings.ambiente}")
    serve(app, host=settings.host, port=settings.port, threads=8)


if __name__ == "__main__":
    main()
