"""Inicia o painel (consulta o TSE em segundo plano e serve a interface).

    python run.py

Configuração por variáveis de ambiente (veja .env.example). Contra o simulador local:
    $env:TSE_BASE="http://127.0.0.1:5001"; $env:TSE_AMBIENTE="simulado"; $env:ESCALA_POLLING="0.25"
"""
from __future__ import annotations

import logging

from waitress import serve

from app import create_app
from app.config import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    app = create_app(settings)
    print(f"Painel em http://{settings.host}:{settings.port}  | fonte: {settings.tse_base}/{settings.ambiente}")
    serve(app, host=settings.host, port=settings.port, threads=8)


if __name__ == "__main__":
    main()
