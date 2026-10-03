"""Armazenamento em memória dos arquivos já interpretados.

Cada chave (ex.: `u:6257:1:br`) guarda o último `Snapshot` válido. Snapshots são imutáveis e
trocados atomicamente, então leitores (a API) nunca esperam pelo poller.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


def chave(tipo: str, ele: str | int = "", cargo: str | int = "", abr: str = "", mun: str | int = "") -> str:
    """Chave canônica: `cfg`, `cm:6257`, `ab:6257:br`, `u:6257:1:sp`, `u:6257:1:sp:71072`."""
    partes = [tipo]
    if ele != "":
        partes.append(str(int(ele)))
    if cargo != "":
        partes.append(str(int(cargo)))
    if abr:
        partes.append(abr.lower())
    if mun != "":
        partes.append(str(int(mun)))
    return ":".join(partes)


@dataclass(frozen=True)
class Snapshot:
    chave: str
    tipo: str  # cfg | cm | ab | u | e
    dados: Any  # saída de app.tse.parse.*
    idg: str
    etag: str | None
    url: str
    meta: dict = field(default_factory=dict)
    obtido_em: float = 0.0  # epoch: última confirmação (200 ou 304)
    mudou_em: float = 0.0  # epoch: última vez que o conteúdo mudou
    conteudo_hash: str = ""  # SHA-1 dos bytes recebidos: é ele (e não o `idg`) que decide se mudou


class Store:
    def __init__(self, *, relogio: Callable[[], float] = time.time):
        self._relogio = relogio
        self._lock = threading.Lock()
        self._itens: dict[str, Snapshot] = {}
        self._versao = 0
        self._ouvintes: list[Callable[[Snapshot], None]] = []

    @property
    def versao(self) -> int:
        """Aumenta a cada mudança de conteúdo; serve para ETag e para detectar novidades."""
        return self._versao

    def ao_mudar(self, ouvinte: Callable[[Snapshot], None]) -> None:
        """Registra uma função chamada (fora do lock) quando o conteúdo de uma chave muda."""
        self._ouvintes.append(ouvinte)

    def get(self, k: str) -> Snapshot | None:
        return self._itens.get(k)

    def dados(self, k: str) -> Any | None:
        s = self._itens.get(k)
        return s.dados if s else None

    def itens(self, prefixo: str = "") -> list[Snapshot]:
        with self._lock:
            return [s for k, s in self._itens.items() if k.startswith(prefixo)]

    def guardar(
        self, k: str, tipo: str, dados: Any, *, idg: str, etag: str | None, url: str,
        meta: dict | None = None, conteudo_hash: str = "",
    ) -> Snapshot:
        """Guarda um conteúdo novo (200 com bytes diferentes dos anteriores, ou primeira carga)."""
        agora = self._relogio()
        snap = Snapshot(k, tipo, dados, idg, etag, url, meta or {}, obtido_em=agora, mudou_em=agora, conteudo_hash=conteudo_hash)
        with self._lock:
            self._itens[k] = snap
            self._versao += 1
        for ouvinte in list(self._ouvintes):
            try:
                ouvinte(snap)
            except Exception:  # um ouvinte com defeito não pode derrubar o poller
                pass
        return snap

    def confirmar(self, k: str, *, etag: str | None = None) -> None:
        """O TSE confirmou (304 ou mesmo `idg`) que nada mudou: só renova o horário de verificação."""
        with self._lock:
            atual = self._itens.get(k)
            if atual is None:
                return
            self._itens[k] = Snapshot(
                atual.chave, atual.tipo, atual.dados, atual.idg, etag or atual.etag, atual.url, atual.meta,
                obtido_em=self._relogio(), mudou_em=atual.mudou_em, conteudo_hash=atual.conteudo_hash,
            )

    def idade_maxima(self, prefixo: str = "") -> float | None:
        """Segundos desde a confirmação mais antiga entre as chaves com o prefixo (None se vazio)."""
        itens = self.itens(prefixo)
        if not itens:
            return None
        return self._relogio() - min(s.obtido_em for s in itens)
