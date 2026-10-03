"""Atribuição estável de cores (slots categóricos 1..8) aos candidatos.

Regra do guia de visualização: a cor segue a PESSOA, nunca a posição no ranking. Por isso um
candidato que aparece entre os primeiros colocados de um escopo ganha o próximo slot livre e o
mantém até o fim, mesmo que depois seja ultrapassado. Quem nunca chegou lá fica no cinza de
"Outros" (slot 0). O estado é gravado em disco para sobreviver a reinícios durante a noite.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

TOP_COM_COR = 3  # só os 3 primeiros colocados ganham cor (limite do mapa, forma "todos contra todos")
MAX_SLOTS = 8
MIN_PCT_SECOES = 1.0  # só atribui depois de 1% das seções totalizadas: o início da apuração é ruidoso


class Cores:
    def __init__(self, arquivo: Path | None = None):
        self._lock = threading.Lock()
        self._slots: dict[str, dict[str, int]] = {}
        self._arquivo = arquivo
        self._carregar()

    def _carregar(self) -> None:
        if not self._arquivo or not self._arquivo.exists():
            return
        try:
            dados = json.loads(self._arquivo.read_text(encoding="utf-8"))
            self._slots = {str(k): {str(sq): int(s) for sq, s in v.items()} for k, v in dados.items()}
        except (OSError, ValueError, AttributeError):
            self._slots = {}  # arquivo ilegível: recomeça (cores só ficam estáveis daqui para frente)

    def _gravar(self) -> None:
        if not self._arquivo:
            return
        try:
            self._arquivo.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._arquivo.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._slots, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self._arquivo)
        except OSError:
            pass  # sem disco, as cores continuam estáveis enquanto o processo viver

    def observar(self, escopo: str, candidatos: list[dict], *, pct_secoes: float) -> bool:
        """Atualiza o escopo com o ranking atual (`candidatos` já ordenado por votos). True se mudou."""
        if pct_secoes < MIN_PCT_SECOES:
            return False
        lideres = [c for c in candidatos[:TOP_COM_COR] if c["votos"] > 0]
        with self._lock:
            mapa = self._slots.setdefault(escopo, {})
            mudou = False
            for c in lideres:
                if c["sq"] in mapa:
                    continue
                livres = [s for s in range(1, MAX_SLOTS + 1) if s not in mapa.values()]
                if not livres:
                    break
                mapa[c["sq"]] = livres[0]
                mudou = True
            if mudou:
                self._gravar()
            return mudou

    def slot(self, escopo: str, sq: str) -> int:
        """Slot 1..8 do candidato, ou 0 (cinza de 'Outros')."""
        return self._slots.get(escopo, {}).get(sq, 0)

    def do_escopo(self, escopo: str) -> dict[str, int]:
        with self._lock:
            return dict(self._slots.get(escopo, {}))
