"""Servidor SIMULADO com o mesmo espaço de URLs do feed do TSE (dados fictícios).

    python -m mock.server --porta 5001 --duracao 600

Aponte o painel para ele:
    $env:TSE_BASE="http://127.0.0.1:5001"; $env:TSE_AMBIENTE="simulado"; $env:ESCALA_POLLING="0.25"

Controle (GET, só para uso local):
    /__sim                       estado da simulação
    /__sim/pausar, /__sim/retomar
    /__sim/velocidade/<x>        ex.: 4 = quatro vezes mais rápido
    /__sim/ir/<pct>              pula para <pct>% da apuração (0 a 120)
    /__sim/falha/<status>/<s>    responde <status> a tudo por <s> segundos (ex.: 503, 429, 404)
    /__sim/falha/limpar
    /__sim/dv/<n|s>              Presidente: n = votação ainda não liberada (votos zerados)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from email.utils import formatdate
from pathlib import Path

from flask import Flask, Response, jsonify, request

from app.tse.dominio import BRASIL, EXTERIOR, UFS

from . import gerador
from .gerador import Simulacao

ELE_PRESIDENTE, ELE_ESTADUAL = 6257, 6259

# Avatar neutro (JPEG de 618 bytes) para as fotos: nada de 404 em foto no simulador
FOTO_JPEG = (Path(__file__).with_name("avatar.jpeg")).read_bytes()

RE_U = re.compile(r"^(?P<abr>[a-z]{2})(?P<mun>\d{5})?-c(?P<cargo>\d{4})-e(?P<ele>\d{6})-u\.json$")
RE_AB = re.compile(r"^(?P<abr>[a-z]{2})-e(?P<ele>\d{6})-ab\.json$")
RE_CM = re.compile(r"^mun-e(?P<ele>\d{6})-cm\.json$")


def criar_app(sim: Simulacao | None = None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    sim = sim or Simulacao()
    app.config["SIM"] = sim

    def responder(corpo: dict | bytes, max_age: int, tipo: str = "application/json") -> Response:
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        etag = '"' + hashlib.md5(dados).hexdigest() + '"'
        resposta = Response(status=304) if request.headers.get("If-None-Match") == etag else Response(dados, mimetype=tipo)
        resposta.headers["ETag"] = etag
        resposta.headers["Cache-Control"] = f"max-age={max_age}"
        resposta.headers["Last-Modified"] = formatdate(usegmt=True)
        return resposta

    @app.before_request
    def injetar_falha():
        if request.path.startswith("/__sim"):
            return None
        if sim.falha_status and time.monotonic() < sim.falha_ate:
            return Response(status=sim.falha_status, headers={"Retry-After": "60"})
        return None

    # ---- feed ------------------------------------------------------------------------------------
    @app.get("/<ambiente>/comum/config/ele-c.json")
    def ele_c(ambiente):
        return responder(gerador.config_eleicoes(sim), 15)

    @app.get("/<ambiente>/<ciclo>/<int:ele>/config/<arquivo>")
    def config(ambiente, ciclo, ele, arquivo):
        m = RE_CM.match(arquivo)
        if not m or int(m["ele"]) != ele or ele not in (ELE_PRESIDENTE, ELE_ESTADUAL):
            return Response(status=404)
        return responder(gerador.municipios(sim, ele), 60)

    @app.get("/<ambiente>/<ciclo>/<int:ele>/dados/<abr>/<arquivo>")
    def dados(ambiente, ciclo, ele, abr, arquivo):
        if abr not in (BRASIL, EXTERIOR) and abr not in UFS:
            return Response(status=404)
        m = RE_AB.match(arquivo)
        if m:
            if m["abr"] != abr or int(m["ele"]) != ele or ele not in (ELE_PRESIDENTE, ELE_ESTADUAL):
                return Response(status=404)
            if abr == EXTERIOR and ele != ELE_PRESIDENTE:
                return Response(status=404)
            return responder(gerador.acompanhamento(sim, ele, abr), 8 if abr == BRASIL else 30)
        m = RE_U.match(arquivo)
        if not m or m["abr"] != abr or int(m["ele"]) != ele:
            return Response(status=404)
        cargo, mun = int(m["cargo"]), (int(m["mun"]) if m["mun"] else None)
        permitido = (ele == ELE_PRESIDENTE and cargo == 1) or (ele == ELE_ESTADUAL and cargo in (3, 5))
        if not permitido or (abr == BRASIL and (cargo != 1 or mun is not None)) or (abr == EXTERIOR and cargo != 1):
            return Response(status=404)
        try:
            corpo = gerador.resultado(sim, ele, cargo, abr, mun)
        except KeyError:  # município inexistente
            return Response(status=404)
        return responder(corpo, 8 if abr == BRASIL else 30)

    @app.get("/<ambiente>/<ciclo>/<int:ele>/fotos/<abr>/<arquivo>")
    def foto(ambiente, ciclo, ele, abr, arquivo):
        return responder(FOTO_JPEG, 3600000, "image/jpeg")

    # ---- controle ----------------------------------------------------------------------------------
    @app.get("/__sim")
    def estado():
        return jsonify(sim.estado())

    @app.get("/__sim/pausar")
    def pausar():
        sim.pausar()
        return jsonify(sim.estado())

    @app.get("/__sim/retomar")
    def retomar():
        sim.retomar()
        return jsonify(sim.estado())

    def numero(texto: str) -> float | None:
        try:
            return float(texto.replace(",", "."))
        except ValueError:
            return None

    @app.get("/__sim/velocidade/<valor>")
    def velocidade(valor):
        v = numero(valor)
        if v is None or v <= 0:
            return jsonify(erro="velocidade deve ser um número positivo"), 400
        sim.velocidade(v)
        return jsonify(sim.estado())

    @app.get("/__sim/ir/<valor>")
    def ir(valor):
        pct = numero(valor)
        if pct is None:
            return jsonify(erro="informe a porcentagem da apuração (0 a 120)"), 400
        sim.ir_para(max(0.0, min(pct, 120.0)) / 100)
        return jsonify(sim.estado())

    @app.get("/__sim/falha/<int:status>/<int:segundos>")
    def falha(status, segundos):
        sim.falha_status, sim.falha_ate = status, time.monotonic() + segundos
        return jsonify(sim.estado())

    @app.get("/__sim/falha/limpar")
    def falha_limpar():
        sim.falha_status, sim.falha_ate = None, 0.0
        return jsonify(sim.estado())

    @app.get("/__sim/dv/<valor>")
    def dv(valor):
        sim.dv_presidente = valor != "n"
        return jsonify(sim.estado())

    return app


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=5001)
    ap.add_argument("--duracao", type=float, default=600.0, help="segundos reais até 100%% da apuração (velocidade 1)")
    ap.add_argument("--velocidade", type=float, default=1.0)
    ap.add_argument("--inicio", type=float, default=0.0, help="fração inicial da apuração (0 a 1)")
    args = ap.parse_args(argv)

    from waitress import serve

    sim = Simulacao(duracao_s=args.duracao, velocidade=args.velocidade, inicio=args.inicio)
    print(f"Simulador do TSE (dados FICTÍCIOS) em http://{args.host}:{args.porta}  | duração {args.duracao:.0f}s | controle em /__sim")
    serve(criar_app(sim), host=args.host, port=args.porta, threads=8)


if __name__ == "__main__":
    main()
