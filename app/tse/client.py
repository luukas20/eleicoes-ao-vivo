"""Cliente HTTP educado para o feed do TSE.

O TSE limita a 100 requisições/s por IP, bloqueia por 10 minutos (renovável a cada nova
tentativa) e pode bloquear também quem requisita URLs inexistentes (404). Por isso este cliente:

* limita a taxa com um token bucket global (padrão bem abaixo do limite);
* usa GET condicional (ETag / Last-Modified) para receber 304 quando nada mudou;
* abre um disjuntor global ao ver 403/429 ou excesso de 404, e para de insistir.
"""
from __future__ import annotations

import collections
import re
import threading
import time
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter

STATUS_REDE = 0  # falha de rede, timeout ou TLS: nenhuma resposta HTTP
STATUS_DISJUNTOR = -1  # requisição nem enviada: disjuntor aberto
BLOQUEIO_S = 11 * 60  # o TSE bloqueia por 10 min; margem para não renovar o bloqueio

_MAX_AGE = re.compile(r"max-age\s*=\s*(\d+)", re.IGNORECASE)


class TokenBucket:
    """Limite de taxa: no máximo `rate` requisições por segundo, com rajada até `burst`."""

    def __init__(self, rate: float, burst: float | None = None, *, clock=time.monotonic, sleep=time.sleep):
        if rate <= 0:
            raise ValueError("rate deve ser positivo")
        self.rate = float(rate)
        self.burst = float(burst) if burst is not None else max(1.0, float(rate))
        self._tokens = self.burst
        self._clock, self._sleep = clock, sleep
        self._last = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Bloqueia até haver uma ficha disponível."""
        while True:
            with self._lock:
                agora = self._clock()
                self._tokens = min(self.burst, self._tokens + (agora - self._last) * self.rate)
                self._last = agora
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                espera = (1.0 - self._tokens) / self.rate
            self._sleep(espera)


class Breaker:
    """Disjuntor global: pausa todas as requisições quando o TSE sinaliza bloqueio ou há muitos 404."""

    def __init__(self, *, clock=time.monotonic, max_404_por_min: int = 10, pausa_404_s: float = 120.0):
        self._clock = clock
        self._lock = threading.Lock()
        self._ate = 0.0
        self._motivo = ""
        self._404: collections.deque[float] = collections.deque()
        self.max_404_por_min = max_404_por_min
        self.pausa_404_s = pausa_404_s
        self.disparos = 0

    @property
    def motivo(self) -> str:
        return self._motivo

    def restante(self) -> float:
        """Segundos até o disjuntor fechar (0 = fechado, requisições liberadas)."""
        with self._lock:
            return max(0.0, self._ate - self._clock())

    def disparar(self, segundos: float, motivo: str) -> None:
        with self._lock:
            self._ate = max(self._ate, self._clock() + segundos)
            self._motivo = motivo
            self.disparos += 1

    def registrar_404(self) -> None:
        agora = self._clock()
        with self._lock:
            self._404.append(agora)
            while self._404 and agora - self._404[0] > 60:
                self._404.popleft()
            excedeu = len(self._404) > self.max_404_por_min
            if excedeu:
                self._404.clear()
        if excedeu:
            self.disparar(self.pausa_404_s, f"mais de {self.max_404_por_min} respostas 404 em 1 minuto")


@dataclass(frozen=True)
class Response:
    url: str
    status: int  # HTTP; STATUS_REDE (0) ou STATUS_DISJUNTOR (-1)
    body: bytes = b""
    etag: str | None = None
    last_modified: str | None = None
    max_age: int | None = None  # segundos, de Cache-Control
    elapsed: float = 0.0
    error: str | None = None
    retry_after: float | None = None  # segundos sugeridos para tentar de novo

    @property
    def ok(self) -> bool:
        return self.status == 200

    @property
    def not_modified(self) -> bool:
        return self.status == 304


class Metrics:
    """Contadores para a página /status."""

    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self.total = 0
        self.por_status: collections.Counter[int] = collections.Counter()
        self.bytes_recebidos = 0
        self._recentes: collections.deque[float] = collections.deque()
        self.ultimo_erro: str | None = None
        self.ultimo_erro_em: float | None = None  # epoch
        self.ultima_resposta_em: float | None = None  # epoch

    def registrar(self, status: int, nbytes: int, erro: str | None = None) -> None:
        with self._lock:
            self.total += 1
            self.por_status[status] += 1
            self.bytes_recebidos += nbytes
            self._recentes.append(self._clock())
            if status > 0:
                self.ultima_resposta_em = time.time()
            if erro:
                self.ultimo_erro, self.ultimo_erro_em = erro, time.time()

    def rps(self, janela: float = 10.0) -> float:
        agora = self._clock()
        with self._lock:
            while self._recentes and agora - self._recentes[0] > 60:
                self._recentes.popleft()
            n = sum(1 for t in self._recentes if agora - t <= janela)
        return round(n / janela, 2)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total": self.total,
                "por_status": {str(k): v for k, v in sorted(self.por_status.items())},
                "bytes_recebidos": self.bytes_recebidos,
                "ultimo_erro": self.ultimo_erro,
                "ultimo_erro_em": self.ultimo_erro_em,
                "ultima_resposta_em": self.ultima_resposta_em,
            }


def _max_age(cabecalho: str | None) -> int | None:
    m = _MAX_AGE.search(cabecalho or "")
    return int(m.group(1)) if m else None


def _retry_after(cabecalho: str | None) -> float | None:
    try:
        return float(cabecalho) if cabecalho else None
    except ValueError:
        return None  # formato de data HTTP: ignorado, o disjuntor usa o prazo padrão


class TseClient:
    """GET condicional com limite de taxa e disjuntor. Seguro para uso por várias threads."""

    def __init__(
        self,
        *,
        user_agent: str,
        max_rps: float = 15.0,
        workers: int = 8,
        connect_timeout: float = 5.0,
        read_timeout: float = 20.0,
        session: requests.Session | None = None,
        bucket: TokenBucket | None = None,
        breaker: Breaker | None = None,
        metrics: Metrics | None = None,
    ):
        self.session = session or self._nova_sessao(user_agent, workers)
        self.bucket = bucket or TokenBucket(max_rps)
        self.breaker = breaker or Breaker()
        self.metrics = metrics or Metrics()
        self.connect_timeout, self.read_timeout = connect_timeout, read_timeout

    @staticmethod
    def _nova_sessao(user_agent: str, workers: int) -> requests.Session:
        sessao = requests.Session()
        sessao.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip"})
        adaptador = HTTPAdapter(pool_connections=2, pool_maxsize=max(4, workers * 2), max_retries=0)
        sessao.mount("https://", adaptador)
        sessao.mount("http://", adaptador)
        return sessao

    def get(self, url: str, *, etag: str | None = None, last_modified: str | None = None) -> Response:
        restante = self.breaker.restante()
        if restante > 0:
            return Response(url, STATUS_DISJUNTOR, error=f"disjuntor aberto ({self.breaker.motivo})", retry_after=restante)

        self.bucket.acquire()
        cabecalhos: dict[str, str] = {}
        if etag:
            cabecalhos["If-None-Match"] = etag
        if last_modified:
            cabecalhos["If-Modified-Since"] = last_modified

        inicio = time.monotonic()
        try:
            r = self.session.get(url, headers=cabecalhos, timeout=(self.connect_timeout, self.read_timeout))
        except requests.RequestException as ex:
            erro = f"{type(ex).__name__}: {ex}"
            self.metrics.registrar(STATUS_REDE, 0, erro=erro)
            return Response(url, STATUS_REDE, error=erro, elapsed=time.monotonic() - inicio)

        conteudo = r.content
        self.metrics.registrar(r.status_code, len(conteudo))
        resposta = Response(
            url,
            r.status_code,
            body=conteudo if r.status_code == 200 else b"",
            etag=r.headers.get("ETag"),
            last_modified=r.headers.get("Last-Modified"),
            max_age=_max_age(r.headers.get("Cache-Control")),
            elapsed=time.monotonic() - inicio,
            retry_after=_retry_after(r.headers.get("Retry-After")),
        )
        if r.status_code in (403, 429):
            self.breaker.disparar(max(BLOQUEIO_S, resposta.retry_after or 0), f"HTTP {r.status_code}")
        elif r.status_code == 404:
            self.breaker.registrar_404()
        return resposta
