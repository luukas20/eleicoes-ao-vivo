"""Contagem de acessos ao painel, para a página de Diagnóstico.

O painel não guarda IP nem nenhum dado pessoal. O que ele conta:

* **páginas abertas**: respostas HTML bem-sucedidas (uma visita = uma página aberta);
* **requisições**: tudo o que o navegador pede (páginas, dados, arquivos, fotos), como o túnel também conta;
* **pessoas online (aproximado)**: aparelhos que fizeram uma consulta de página ou de dados na última janela. O navegador
  consulta a cada 10 s com a página à vista (aba escondida não consulta). Cada aparelho vira um código curto e
  irreversível (hash com sal sorteado a cada partida), que só existe na memória e some depois da janela;
* **picos** (online, requisições por minuto, requisições em andamento) com o horário em que aconteceram.

Tudo é contado em dois grupos: **pelo link público** (requisições que chegam pelo túnel da Cloudflare, que identifica o
visitante no cabeçalho `CF-Connecting-IP`) e **todos** (inclui este computador e a rede local). Os totais e os picos
ficam em um arquivo pequeno em `data/acessos/` e sobrevivem a reinícios; quem está online não.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .tse.parse import BRT

JANELA_ONLINE_S = 35  # o navegador consulta a cada 10 s; três consultas perdidas e o aparelho deixa de contar
JANELA_MINUTO_S = 60
SALVAR_A_CADA_S = 30.0
IGNORADOS = ("/status", "/api/v1/status", "/healthz")  # o próprio diagnóstico não entra na conta
SEM_PRESENCA = ("/static/", "/foto/")  # arquivos e fotos contam como requisição, mas não indicam alguém com a página aberta


def ignorar(caminho: str) -> bool:
    return caminho in IGNORADOS


def _iso(epoch: float | None) -> str | None:
    if not epoch:
        return None
    from datetime import datetime

    return datetime.fromtimestamp(epoch, BRT).isoformat(timespec="seconds")


class _Escopo:
    """Contadores de um grupo (link público ou todos)."""

    def __init__(self) -> None:
        self.paginas = 0
        self.requisicoes = 0
        self.em_andamento = 0
        self.visto: dict[str, float] = {}  # aparelho (hash) -> última consulta
        self.por_segundo: dict[int, int] = {}  # segundo -> requisições (só os últimos 60 s)
        self.online = 0
        self.req_por_min = 0
        self.pico_online: tuple[int, float | None] = (0, None)
        self.pico_req_min: tuple[int, float | None] = (0, None)
        self.pico_em_andamento: tuple[int, float | None] = (0, None)

    def abrir(self, agora: float, aparelho: str | None) -> None:
        self.requisicoes += 1
        self.em_andamento += 1
        if self.em_andamento > self.pico_em_andamento[0]:
            self.pico_em_andamento = (self.em_andamento, agora)
        segundo = int(agora)
        self.por_segundo[segundo] = self.por_segundo.get(segundo, 0) + 1
        if aparelho is not None:
            self.visto[aparelho] = agora

    def fechar(self) -> None:
        self.em_andamento = max(0, self.em_andamento - 1)

    def atualizar(self, agora: float) -> None:
        """Descarta o que saiu da janela e confere se há pico novo (chamado no máximo uma vez por segundo)."""
        corte = agora - JANELA_ONLINE_S
        if any(t < corte for t in self.visto.values()):
            self.visto = {a: t for a, t in self.visto.items() if t >= corte}
        self.online = len(self.visto)
        if self.online > self.pico_online[0]:
            self.pico_online = (self.online, agora)
        limite = int(agora) - JANELA_MINUTO_S
        self.por_segundo = {s: n for s, n in self.por_segundo.items() if s > limite}
        self.req_por_min = sum(self.por_segundo.values())
        if self.req_por_min > self.pico_req_min[0]:
            self.pico_req_min = (self.req_por_min, agora)

    def dados(self) -> dict[str, Any]:
        def pico(p: tuple[int, float | None]) -> dict[str, Any]:
            return {"n": p[0], "em": _iso(p[1])}

        return {
            "paginas": self.paginas, "requisicoes": self.requisicoes,
            "online": self.online, "pico_online": pico(self.pico_online),
            "req_por_min": self.req_por_min, "pico_req_por_min": pico(self.pico_req_min),
            "em_andamento": self.em_andamento, "pico_em_andamento": pico(self.pico_em_andamento),
        }

    def para_disco(self) -> dict[str, Any]:
        return {
            "paginas": self.paginas, "requisicoes": self.requisicoes, "pico_online": list(self.pico_online),
            "pico_req_min": list(self.pico_req_min), "pico_em_andamento": list(self.pico_em_andamento),
        }

    def de_disco(self, d: dict[str, Any]) -> None:
        def par(valor: Any) -> tuple[int, float | None]:
            n, quando = valor
            return int(n), (float(quando) if quando else None)

        self.paginas = int(d.get("paginas", 0))
        self.requisicoes = int(d.get("requisicoes", 0))
        self.pico_online = par(d.get("pico_online", (0, None)))
        self.pico_req_min = par(d.get("pico_req_min", (0, None)))
        self.pico_em_andamento = par(d.get("pico_em_andamento", (0, None)))


class Acessos:
    def __init__(self, arquivo: Path | None = None, *, relogio: Callable[[], float] = time.time):
        self._relogio = relogio
        self._arquivo = arquivo
        self._lock = threading.Lock()
        self._lock_arquivo = threading.Lock()
        self._sal = secrets.token_bytes(8)
        self.todos = _Escopo()
        self.link = _Escopo()
        self.desde = relogio()
        self._ultimo_tick = 0.0
        self._ultimo_salvamento = relogio()
        self._sujo = False
        self._carregar()
        atexit.register(self.salvar)  # parada normal (Ctrl+C) grava na hora; queda brusca perde no máximo 30 s

    # ---- ciclo de cada requisição --------------------------------------------------------------------
    def abrir(self, caminho: str, via_link: bool, cliente: str) -> None:
        """Começo de uma requisição. `cliente`: o que identifica o aparelho (IP e navegador); não é guardado."""
        agora = self._relogio()
        aparelho = None
        if not caminho.startswith(SEM_PRESENCA):
            aparelho = hashlib.sha1(self._sal + cliente.encode("utf-8", "replace")).hexdigest()[:12]
        with self._lock:
            self.todos.abrir(agora, aparelho)
            if via_link:
                self.link.abrir(agora, aparelho)
            self._sujo = True
            if agora - self._ultimo_tick >= 1.0:
                self._atualizar(agora)
        self._salvar_se_for_hora(agora)

    def fechar(self, via_link: bool) -> None:
        with self._lock:
            self.todos.fechar()
            if via_link:
                self.link.fechar()

    def pagina(self, via_link: bool) -> None:
        with self._lock:
            self.todos.paginas += 1
            if via_link:
                self.link.paginas += 1

    # ---- leitura -------------------------------------------------------------------------------------
    def _atualizar(self, agora: float) -> None:
        self._ultimo_tick = agora
        self.todos.atualizar(agora)
        self.link.atualizar(agora)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._atualizar(self._relogio())
            return {
                "desde": _iso(self.desde), "janela_online_s": JANELA_ONLINE_S,
                "link": self.link.dados(), "todos": self.todos.dados(),
            }

    # ---- disco ---------------------------------------------------------------------------------------
    def _salvar_se_for_hora(self, agora: float) -> None:
        if self._sujo and agora - self._ultimo_salvamento >= SALVAR_A_CADA_S:
            self.salvar()

    def salvar(self) -> None:
        if self._arquivo is None:
            return
        with self._lock:
            conteudo = {"desde": self.desde, "todos": self.todos.para_disco(), "link": self.link.para_disco()}
            self._sujo = False
            self._ultimo_salvamento = self._relogio()
        with self._lock_arquivo:
            try:
                self._arquivo.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._arquivo.with_suffix(".tmp")
                tmp.write_text(json.dumps(conteudo, separators=(",", ":")), encoding="utf-8")
                os.replace(tmp, self._arquivo)
            except OSError:
                pass  # sem disco a contagem continua valendo enquanto o painel estiver de pé

    def _carregar(self) -> None:
        if self._arquivo is None or not self._arquivo.exists():
            return
        try:
            d = json.loads(self._arquivo.read_text(encoding="utf-8"))
            self.todos.de_disco(d["todos"])
            self.link.de_disco(d["link"])
            self.desde = float(d.get("desde") or self.desde)
        except (OSError, ValueError, KeyError, TypeError):
            self.todos, self.link = _Escopo(), _Escopo()  # arquivo ilegível: recomeça do zero, sem derrubar o painel
