"""Agendador de consultas ao TSE.

Uma thread agenda e um pool pequeno executa. Cada alvo tem o seu próprio intervalo:

* começa no piso da camada, respeitando o `max-age` informado pelo CDN (limitado ao teto);
* se nada mudou (304 ou mesmo `idg`), recua x1,5 até o teto; se mudou, volta ao piso;
* erros de rede/5xx recuam exponencialmente; 404 espera bastante; 403/429 abrem o disjuntor
  global do cliente e todos os alvos esperam.

As eleições a acompanhar vêm do EA11 (arquivo `cfg`): quando ele muda, os alvos são sincronizados.
"""
from __future__ import annotations

import hashlib
import logging
import random
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from .catalog import Alvo, disputas_ativas, montar_alvos
from .config import Settings
from .store import Store, chave
from .tse import parse
from .tse.client import STATUS_DISJUNTOR, TseClient
from .tse.urls import TseUrls

log = logging.getLogger("poller")


@dataclass(frozen=True)
class Camada:
    nome: str
    piso: float  # s: menor intervalo entre consultas do mesmo arquivo
    teto: float  # s: maior intervalo depois de recuos


CAMADAS: dict[str, Camada] = {
    c.nome: c
    for c in (
        Camada("config", 45, 120),  # EA11: quase não muda
        Camada("nacional", 8, 20),  # Presidente BR + EA14: o que mais gente acompanha
        Camada("uf", 15, 45),  # Presidente/Governador/Senador por UF
        Camada("uf_lento", 30, 90),  # deputados por UF (arquivos grandes)
        Camada("estatico", 300, 900),  # EA12: municípios e zonas
        Camada("sob_demanda", 20, 60),  # município/UF em foco enquanto houver visitante
    )
}

ESPERA_404_S = 300.0  # arquivo ainda inexistente: não insistir (404 repetido pode bloquear o IP)

PARSERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "cfg": parse.parse_config_eleicoes,
    "cm": parse.parse_municipios,
    "ab": parse.parse_acompanhamento,
    "u": parse.parse_resultado,
    "e": parse.parse_eleitos,
}


class _Estado:
    """Estado de agendamento de um alvo."""

    def __init__(self, alvo: Alvo, camada: Camada, intervalo: float, proxima: float, expira_em: float | None = None):
        self.alvo = alvo
        self.camada = camada
        self.intervalo = intervalo
        self.proxima = proxima
        self.expira_em = expira_em
        self.etag: str | None = None
        self.last_modified: str | None = None
        self.falhas = 0
        self.em_voo = False
        self.ultimo_status: int | None = None
        self.ultimo_erro: str | None = None
        self.ultima_consulta: float | None = None  # epoch


class _ExecutorSincrono:
    """Executor que roda na hora, na mesma thread (para testes)."""

    def submit(self, fn, *args):
        fn(*args)


class Poller:
    def __init__(
        self,
        settings: Settings,
        client: TseClient,
        store: Store,
        *,
        relogio: Callable[[], float] = time.monotonic,
        aleatorio: random.Random | None = None,
        executor: Any = None,
    ):
        self.cfg, self.client, self.store = settings, client, store
        self._relogio = relogio
        self._rnd = aleatorio or random.Random()
        self._executor = executor or ThreadPoolExecutor(max_workers=settings.workers, thread_name_prefix="tse")
        self._lock = threading.RLock()
        self._estados: dict[str, _Estado] = {}
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self.iniciado_em: float | None = None
        store.ao_mudar(self._ao_mudar_store)

    # ---- ciclo de vida -----------------------------------------------------------------------------
    def iniciar(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.iniciado_em = time.time()
        self._adicionar(self._alvo_config(), inicio_imediato=True)
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, name="poller", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=5)
        if hasattr(self._executor, "shutdown"):
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _loop(self) -> None:
        while not self._parar.wait(0.25):
            try:
                self._tick()
            except Exception:  # o agendador nunca pode morrer
                log.exception("falha no agendador")

    # ---- alvos -------------------------------------------------------------------------------------
    def _alvo_config(self) -> Alvo:
        url = TseUrls(self.cfg.tse_base, self.cfg.ambiente, "").config_eleicoes()
        return Alvo(chave("cfg"), "cfg", url, "config", {})

    def _escala(self) -> float:
        return self.cfg.escala_polling

    def _adicionar(self, alvo: Alvo, *, inicio_imediato: bool = False, ttl: float | None = None) -> _Estado:
        with self._lock:
            existente = self._estados.get(alvo.chave)
            if existente:
                if ttl is not None and existente.expira_em is not None:
                    existente.expira_em = max(existente.expira_em, self._relogio() + ttl)
                return existente
            camada = CAMADAS[alvo.camada]
            piso = camada.piso * self._escala()
            # espalha a primeira consulta de cada alvo para não disparar uma rajada de uma vez só
            atraso = 0.0 if inicio_imediato else self._rnd.uniform(0, max(piso, 1.0))
            estado = _Estado(
                alvo, camada, piso, self._relogio() + atraso,
                expira_em=self._relogio() + ttl if ttl is not None else None,
            )
            self._estados[alvo.chave] = estado
            return estado

    def solicitar(self, alvo: Alvo, ttl: float = 90.0) -> bool:
        """Alvo sob demanda (município em foco): consultado enquanto alguém renovar o pedido.

        Devolve False (sem criar nada) quando já há `max_sob_demanda` alvos desse tipo, para os pedidos
        dos visitantes nunca ameaçarem o limite de requisições ao TSE."""
        with self._lock:
            novo = alvo.chave not in self._estados
            cheio = sum(1 for e in self._estados.values() if e.expira_em is not None) >= self.cfg.max_sob_demanda
        if novo and cheio:
            return False
        self._adicionar(alvo, inicio_imediato=True, ttl=ttl)
        return True

    def sincronizar(self) -> int:
        """Cria os alvos derivados do EA11 já carregado. Devolve quantos alvos existem ao todo."""
        snap = self.store.get(chave("cfg"))
        if snap is None:
            return len(self._estados)
        disputas = disputas_ativas(snap.dados, so=self.cfg.eleicoes, cargos=self.cfg.cargos)
        dirs = snap.dados.get("dirs", {})

        def urls_do_ciclo(ciclo: str) -> TseUrls:
            return TseUrls(self.cfg.tse_base, self.cfg.ambiente, ciclo, dirs)

        for alvo in montar_alvos(disputas, urls_do_ciclo):
            # arquivos "estáticos" (lista de municípios) mudam pouco, mas a busca de municípios depende deles:
            # buscar já na partida; o resto espalha a primeira consulta para não disparar uma rajada
            self._adicionar(alvo, inicio_imediato=alvo.camada == "estatico")
        with self._lock:
            return len(self._estados)

    def _ao_mudar_store(self, snap) -> None:
        if snap.tipo == "cfg":
            try:
                total = self.sincronizar()
                log.info("configuração do TSE (idg %s): %d alvos", snap.idg, total)
            except Exception:
                log.exception("falha ao sincronizar alvos com o EA11")

    # ---- agendamento -------------------------------------------------------------------------------
    def _tick(self) -> None:
        agora = self._relogio()
        with self._lock:
            for k in [k for k, e in self._estados.items() if e.expira_em is not None and e.expira_em <= agora and not e.em_voo]:
                del self._estados[k]
            devidos = sorted(
                (e for e in self._estados.values() if not e.em_voo and e.proxima <= agora),
                key=lambda e: e.proxima,
            )
            for e in devidos:
                e.em_voo = True
        for e in devidos:
            self._executor.submit(self._executar, e)

    def _reagendar(self, e: _Estado, segundos: float) -> None:
        e.proxima = self._relogio() + segundos * self._rnd.uniform(0.9, 1.1)

    def _executar(self, e: _Estado) -> None:
        try:
            resposta = self.client.get(e.alvo.url, etag=e.etag, last_modified=e.last_modified)
            e.ultima_consulta = time.time()
            self._tratar(e, resposta)
        except Exception as ex:  # defeito nosso (ex.: parse): registra, recua e segue
            e.falhas += 1
            e.ultimo_erro = f"{type(ex).__name__}: {ex}"
            log.exception("erro ao processar %s", e.alvo.chave)
            self._reagendar(e, min(5 * 2 ** (e.falhas - 1), 120))
        finally:
            e.em_voo = False

    def _tratar(self, e: _Estado, r) -> None:
        e.ultimo_status = r.status
        piso, teto = e.camada.piso * self._escala(), e.camada.teto * self._escala()

        if r.status == 200:
            bruto = parse.decodificar(r.body)
            # O que decide se há dado novo é o CONTEÚDO (hash dos bytes), não o `idg`: se o TSE regenerar o
            # arquivo sem trocar o identificador, o painel não pode ficar parado em dado velho.
            huella = hashlib.sha1(r.body).hexdigest()
            e.etag = r.etag or e.etag
            e.last_modified = r.last_modified or e.last_modified
            atual = self.store.get(e.alvo.chave)
            mudou = atual is None or atual.conteudo_hash != huella
            if mudou:
                self.store.guardar(
                    e.alvo.chave, e.alvo.tipo, PARSERS[e.alvo.tipo](bruto),
                    idg=str(bruto.get("idg", "")), etag=r.etag, url=e.alvo.url, meta=e.alvo.meta, conteudo_hash=huella,
                )
            else:
                self.store.confirmar(e.alvo.chave, etag=r.etag)
            e.falhas, e.ultimo_erro = 0, None
            self._apos_sucesso(e, r, mudou, piso, teto)
        elif r.status == 304:
            self.store.confirmar(e.alvo.chave)
            e.falhas, e.ultimo_erro = 0, None
            self._apos_sucesso(e, r, False, piso, teto)
        elif r.status == 404:
            e.ultimo_erro = "404: arquivo ainda não disponível"
            e.intervalo = max(ESPERA_404_S * self._escala(), teto)
            self._reagendar(e, e.intervalo)
        elif r.status == STATUS_DISJUNTOR:
            e.ultimo_erro = r.error
            self._reagendar(e, max(r.retry_after or 30.0, 10.0))
        else:  # falha de rede (0), 5xx ou outro status inesperado
            e.falhas += 1
            e.ultimo_erro = r.error or f"HTTP {r.status}"
            self._reagendar(e, min(5 * 2 ** (e.falhas - 1), 120))

    def _apos_sucesso(self, e: _Estado, r, mudou: bool, piso: float, teto: float) -> None:
        intervalo = piso if mudou else min(max(e.intervalo, piso) * 1.5, teto)
        if r.max_age:  # respeita o CDN: pedir antes disso só devolveria o mesmo conteúdo
            intervalo = max(intervalo, min(float(r.max_age), teto))
        e.intervalo = intervalo
        self._reagendar(e, intervalo)

    # ---- diagnóstico (página /status) ------------------------------------------------------------------
    def estado(self) -> dict[str, Any]:
        agora_epoch = time.time()
        with self._lock:
            estados = list(self._estados.values())
        por_camada: dict[str, dict[str, Any]] = {}
        for nome in CAMADAS:
            da_camada = [e for e in estados if e.camada.nome == nome]
            if da_camada:
                por_camada[nome] = {
                    "alvos": len(da_camada),
                    "intervalo_medio_s": round(sum(e.intervalo for e in da_camada) / len(da_camada), 1),
                }
        status = Counter(e.ultimo_status for e in estados if e.ultimo_status is not None)
        problemas = [
            {"chave": e.alvo.chave, "status": e.ultimo_status, "erro": e.ultimo_erro, "falhas": e.falhas}
            for e in estados
            if e.ultimo_erro
        ]
        problemas.sort(key=lambda p: (p["status"] == 404, p["chave"]))  # erros de rede/5xx antes dos 404
        m = self.client.metrics
        disjuntor = self.client.breaker
        return {
            "rodando": bool(self._thread and self._thread.is_alive()),
            "iniciado_em": self.iniciado_em,
            "agora": agora_epoch,
            "alvos": len(estados),
            "em_voo": sum(1 for e in estados if e.em_voo),
            "camadas": por_camada,
            "ultimo_status_por_alvo": {str(k): v for k, v in sorted(status.items())},
            "total_com_problema": len(problemas),
            "com_problema": problemas[:50],
            "cliente": {
                **m.snapshot(),
                "req_por_s": m.rps(),
                "limite_req_por_s": self.client.bucket.rate,
                "disjuntor": {
                    "aberto": disjuntor.restante() > 0,
                    "restante_s": round(disjuntor.restante(), 1),
                    "motivo": disjuntor.motivo,
                    "disparos": disjuntor.disparos,
                },
            },
        }
