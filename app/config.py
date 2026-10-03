"""Configuração por variáveis de ambiente (veja .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

USER_AGENT_PADRAO = "eleicoes-ao-vivo/0.1 (+https://github.com/luukas20/eleicoes-ao-vivo; painel nao oficial)"


def _float(nome: str, padrao: float) -> float:
    try:
        return float(os.environ[nome])
    except (KeyError, ValueError):
        return padrao


def _int(nome: str, padrao: int) -> int:
    try:
        return int(os.environ[nome])
    except (KeyError, ValueError):
        return padrao


@dataclass(frozen=True)
class Settings:
    tse_base: str = "https://resultados.tse.jus.br"
    ambiente: str = "oficial"
    eleicoes: tuple[str, ...] = ()  # vazio = descobrir pelo EA11
    cargos: tuple[int, ...] = (1, 3, 5)  # só consulta o que o painel exibe: Presidente, Governador, Senador
    user_agent: str = USER_AGENT_PADRAO
    max_rps: float = 15.0  # teto global de requisições/s ao TSE (o limite deles é 100)
    workers: int = 8
    escala_polling: float = 1.0  # multiplica os intervalos de consulta (testes usam < 1)
    desatualizado_apos_s: int = 120  # sem consulta bem-sucedida há tanto tempo => aviso na tela
    data_dir: Path = RAIZ / "data"
    host: str = "127.0.0.1"
    port: int = 8000
    iniciar_poller: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        base = cls()
        return replace(
            base,
            tse_base=e.get("TSE_BASE", base.tse_base).rstrip("/"),
            ambiente=e.get("TSE_AMBIENTE", base.ambiente),
            eleicoes=tuple(x.strip() for x in e.get("TSE_ELEICOES", "").split(",") if x.strip()),
            cargos=tuple(int(x) for x in e.get("CARGOS", "").split(",") if x.strip().isdigit()) or base.cargos,
            user_agent=e.get("USER_AGENT", base.user_agent),
            max_rps=_float("MAX_RPS", base.max_rps),
            workers=_int("WORKERS", base.workers),
            escala_polling=_float("ESCALA_POLLING", base.escala_polling),
            desatualizado_apos_s=_int("DESATUALIZADO_APOS_S", base.desatualizado_apos_s),
            data_dir=Path(e.get("DATA_DIR", str(base.data_dir))),
            host=e.get("HOST", base.host),
            port=_int("PORT", base.port),
            iniciar_poller=e.get("INICIAR_POLLER", "1") not in ("0", "false", "False"),
        )
