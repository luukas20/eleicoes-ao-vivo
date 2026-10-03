"""Cache em disco das fotos dos candidatos (o TSE manda `max-age` de ~42 dias; foto não muda).

Os navegadores pedem à NOSSA rota `/foto/...`; só o servidor fala com o TSE, uma vez por foto.
Foto inexistente (404) entra num cache negativo temporário para não repetir a requisição, pois
404 repetido pode bloquear o IP.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from .tse.client import TseClient

NEGATIVO_S = 600.0  # quanto tempo lembrar que uma foto não existe


class FotoCache:
    def __init__(self, pasta: Path, client: TseClient, *, relogio=time.monotonic):
        self.pasta = pasta
        self.client = client
        self._relogio = relogio
        self._lock = threading.Lock()
        self._travas: dict[str, threading.Lock] = {}
        self._ausentes: dict[str, float] = {}

    def _caminho(self, ele: int, escopo: str, sq: str) -> Path:
        return self.pasta / str(ele) / escopo / f"{sq}.jpeg"

    def obter(self, ele: int, escopo: str, sq: str, url: str) -> bytes | None:
        """Bytes da foto (do disco ou baixada agora) ou None se não existir/indisponível."""
        chave = f"{ele}/{escopo}/{sq}"
        caminho = self._caminho(ele, escopo, sq)
        if caminho.exists():
            return caminho.read_bytes()
        with self._lock:
            ate = self._ausentes.get(chave)
            if ate is not None and self._relogio() < ate:
                return None
            trava = self._travas.setdefault(chave, threading.Lock())
        with trava:  # várias pessoas pedindo a mesma foto ao mesmo tempo => uma única ida ao TSE
            if caminho.exists():
                return caminho.read_bytes()
            resposta = self.client.get(url)
            if resposta.ok and resposta.body[:2] == b"\xff\xd8":  # confere que é JPEG de verdade
                caminho.parent.mkdir(parents=True, exist_ok=True)
                tmp = caminho.with_suffix(".tmp")
                tmp.write_bytes(resposta.body)
                os.replace(tmp, caminho)
                return resposta.body
            with self._lock:
                self._ausentes[chave] = self._relogio() + (NEGATIVO_S if resposta.status in (404, 200) else 30.0)
            return None
