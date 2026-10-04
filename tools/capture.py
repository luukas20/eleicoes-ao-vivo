"""Baixa, com educação, um conjunto pequeno de arquivos reais do TSE para usar como fixtures.

Uso:  python -m tools.capture [--out tests/fixtures/tse] [--pausa 0.5] [--so TRECHO]

Cada arquivo é salvo exatamente como recebido (sem alterar o conteúdo, Art. 267 §4 da
Res. TSE 23.751/2026), preservando o caminho relativo à base do TSE, e um MANIFEST.json registra
URL, horário, tamanho e SHA-256. Só arquivos pequenos entram (os grandes ficam fora do repositório).
`--so` captura apenas os alvos cuja descrição contém o trecho e acrescenta ao manifesto existente.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.tse.client import TseClient
from app.tse.urls import TseUrls, como_jws

LIMITE_BYTES = 30_000  # fixtures reais pequenos; o resto é sintético ou marcado como "live"
LIMITE_DEPUTADO_BYTES = 120_000  # o menor arquivo de deputados (Distrital do DF) tem ~97 KB; os das demais UFs são maiores
ELE_PRESIDENTE, ELE_ESTADUAL = 6257, 6259


def alvos(urls: TseUrls) -> list[tuple[str, str, int]]:
    """(descrição, URL, limite de bytes) dos arquivos a capturar."""
    presidente_br = urls.resultado(ELE_PRESIDENTE, 1, "br")
    return [
        ("EA11 configuração de eleições", urls.config_eleicoes(), LIMITE_BYTES),
        ("EA14 acompanhamento Brasil", urls.acompanhamento(ELE_PRESIDENTE, "br"), LIMITE_BYTES),
        ("EA20 Presidente BR", presidente_br, LIMITE_BYTES),
        ("EA20 Presidente BR (assinado)", como_jws(presidente_br), LIMITE_BYTES),
        ("EA20 Presidente exterior", urls.resultado(ELE_PRESIDENTE, 1, "zz"), LIMITE_BYTES),
        ("EA20 Presidente São Paulo (município)", urls.resultado(ELE_PRESIDENTE, 1, "sp", municipio=71072), LIMITE_BYTES),
        ("EA20 Governador SP", urls.resultado(ELE_ESTADUAL, 3, "sp"), LIMITE_BYTES),
        ("EA20 Deputado Distrital DF", urls.resultado(ELE_ESTADUAL, 8, "df"), LIMITE_DEPUTADO_BYTES),
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("tests/fixtures/tse"))
    ap.add_argument("--pausa", type=float, default=0.5, help="segundos entre requisições")
    ap.add_argument("--so", default="", help="captura só os alvos cuja descrição contém este trecho (e mescla no manifesto)")
    args = ap.parse_args(argv)

    cfg = Settings.from_env()
    urls = TseUrls(cfg.tse_base, cfg.ambiente, "ele2026")
    cliente = TseClient(user_agent=cfg.user_agent, max_rps=2.0, workers=1)
    manifesto: list[dict] = []
    erros = 0

    for descricao, url, limite in alvos(urls):
        if args.so and args.so.lower() not in descricao.lower():
            continue
        resposta = cliente.get(url)
        if not resposta.ok:
            print(f"[ERRO] {descricao}: HTTP {resposta.status} {resposta.error or ''} <- {url}")
            erros += 1
            if cliente.breaker.restante() > 0:
                print("Disjuntor aberto; interrompendo para não insistir.")
                break
            time.sleep(args.pausa)
            continue
        if len(resposta.body) > limite:
            print(f"[PULOU] {descricao}: {len(resposta.body)} bytes > {limite}")
            continue
        relativo = url.removeprefix(cfg.tse_base.rstrip("/") + "/")
        destino = args.out / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(resposta.body)
        manifesto.append(
            {
                "descricao": descricao,
                "url": url,
                "arquivo": relativo,
                "capturado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "bytes": len(resposta.body),
                "sha256": hashlib.sha256(resposta.body).hexdigest(),
                "etag": resposta.etag,
            }
        )
        print(f"[ok] {descricao}: {len(resposta.body)} bytes -> {destino}")
        time.sleep(args.pausa)

    args.out.mkdir(parents=True, exist_ok=True)
    arquivo_manifesto = args.out / "MANIFEST.json"
    if args.so and arquivo_manifesto.exists():  # captura parcial: mantém as entradas anteriores e troca só as recapturadas
        novos = {m["arquivo"] for m in manifesto}
        manifesto = [m for m in json.loads(arquivo_manifesto.read_text(encoding="utf-8")) if m["arquivo"] not in novos] + manifesto
    arquivo_manifesto.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(manifesto)} arquivo(s) salvos em {args.out}; {erros} erro(s).")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
