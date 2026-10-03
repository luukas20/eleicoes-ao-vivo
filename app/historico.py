"""Histórico da apuração: série temporal do percentual de cada candidato, gravada a cada totalização nova.

O TSE só publica o estado ATUAL de cada arquivo; a evolução só existe porque o painel a registra.
Por isso o painel precisa estar no ar desde antes da apuração para ter a curva completa. Os pontos
vão para arquivos JSONL (um por disputa/abrangência) e são recarregados ao reiniciar.

Só entra ponto novo quando os números mudaram de verdade (seções ou votos); regenerações do arquivo
sem mudança não poluem a curva. Se a apuração "voltar" (menos da metade das seções do último ponto),
a série recomeça: acontece ao reiniciar o simulador ou se o TSE publicar uma apuração nova.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

MAX_PONTOS = 20000  # por série; 4 h de apuração com um ponto a cada 10 s são ~1.440
FRACAO_QUE_REINICIA = 0.5


def amostrar(pontos: list[Any], limite: int) -> list[Any]:
    """No máximo `limite` itens, espaçados por igual, sempre mantendo o primeiro e o último."""
    n = len(pontos)
    if n <= limite or limite < 2:
        return list(pontos)
    indices = {round(i * (n - 1) / (limite - 1)) for i in range(limite)}
    return [pontos[i] for i in sorted(indices)]


class Historico:
    def __init__(self, pasta: Path | None = None):
        self._lock = threading.Lock()
        self._pasta = pasta
        self._series: dict[str, list[dict[str, Any]]] = {}
        self._carregar()

    # ---- leitura -------------------------------------------------------------------------------------
    def serie(self, chave: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._series.get(chave, ()))

    def chaves(self) -> list[str]:
        with self._lock:
            return sorted(self._series)

    # ---- escrita -------------------------------------------------------------------------------------
    def registrar(self, chave: str, resultado: dict[str, Any]) -> bool:
        """Registra o estado atual de um resultado (saída de `parse_resultado`). True se entrou ponto novo."""
        secoes = resultado["secoes"]
        st = secoes.get("st", 0)
        candidatos = [c for c in resultado["candidatos"] if c["votos"] > 0]
        vv = sum(c["votos"] for c in candidatos)
        if st <= 0 or vv <= 0 or not resultado["estado"]["divulga"]:
            return False
        ponto = {
            "t": resultado["totalizado_em"] or resultado["gerado_em"],
            "st": st,
            "ts": secoes.get("ts", 0),
            "pst": secoes["pst"]["n"] if "pst" in secoes else 0.0,
            "vv": vv,
            "c": {c["sq"]: [c["votos"], c["pct"]["n"]] for c in candidatos},
        }
        with self._lock:
            serie = self._series.setdefault(chave, [])
            reiniciar = False
            if serie:
                ultimo = serie[-1]
                if (st, vv) == (ultimo["st"], ultimo["vv"]):
                    return False
                if st < ultimo["st"] * FRACAO_QUE_REINICIA:
                    serie.clear()
                    reiniciar = True
            serie.append(ponto)
            cortou = len(serie) > MAX_PONTOS
            if cortou:
                del serie[: MAX_PONTOS // 10]
            self._gravar(chave, ponto, regravar=serie if (reiniciar or cortou) else None)
        return True

    # ---- disco ---------------------------------------------------------------------------------------
    def _arquivo(self, chave: str) -> Path | None:
        return self._pasta / (chave.replace(":", "_") + ".jsonl") if self._pasta else None

    def _gravar(self, chave: str, ponto: dict[str, Any], *, regravar: list[dict[str, Any]] | None) -> None:
        caminho = self._arquivo(chave)
        if caminho is None:
            return
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            if regravar is not None:  # série recomeçou ou foi aparada: regrava o arquivo inteiro
                tmp = caminho.with_suffix(".tmp")
                tmp.write_text("".join(json.dumps(p, separators=(",", ":")) + "\n" for p in regravar), encoding="utf-8")
                os.replace(tmp, caminho)
            else:
                with caminho.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(ponto, separators=(",", ":")) + "\n")
        except OSError:
            pass  # sem disco o histórico continua valendo enquanto o processo viver

    def _carregar(self) -> None:
        if not self._pasta or not self._pasta.exists():
            return
        for arquivo in self._pasta.glob("*.jsonl"):
            pontos = []
            try:
                for linha in arquivo.read_text(encoding="utf-8").splitlines()[-MAX_PONTOS:]:
                    try:
                        p = json.loads(linha)
                        if isinstance(p, dict) and "c" in p and "t" in p:
                            pontos.append(p)
                    except ValueError:
                        continue  # linha cortada no meio por uma queda de energia: ignora
            except OSError:
                continue
            if pontos:
                self._series[arquivo.stem.replace("_", ":")] = pontos
