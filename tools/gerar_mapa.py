"""Gera `app/static/data/mapa-ufs.json`: os contornos das UFs, já projetados e simplificados, para o mapa do painel.

    python -m tools.gerar_mapa                       # baixa a malha das UFs no IBGE (uma vez) e grava o arquivo
    python -m tools.gerar_mapa --entrada uf.geojson  # usa um GeoJSON que já está no disco

O painel NÃO consulta o IBGE em tempo de execução: o arquivo gerado é versionado no repositório e o navegador só o
baixa do próprio painel. O que este script faz com a malha:

1. projeta lon/lat com a cônica equivalente de Albers (a projeção usada pelo IBGE nos mapas do Brasil), em uma tela de
   LARGURA unidades de largura (1 unidade ≈ 4,5 km);
2. simplifica os contornos por *arcos*: um trecho de fronteira compartilhado por dois estados é simplificado uma única
   vez, então os vizinhos continuam encaixados, sem frestas nem sobreposição;
3. grava cada UF como um caminho SVG com coordenadas inteiras e relativas (pequeno), em ordem alfabética do nome;
4. para o rótulo "SP", grava o ponto onde cabe a maior caixa de texto dentro do estado (`x`, `y`, `lw`) e até onde vai a
   costa naquela linha (`e`), usado para as chamadas (etiquetas ao lado) dos estados pequenos.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import unicodedata
from pathlib import Path

from app.tse.dominio import UF_NOMES

IBGE_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    "?formato=application/vnd.geo+json&qualidade={qualidade}&intrarregiao=UF"
)
DESTINO = Path(__file__).resolve().parent.parent / "app" / "static" / "data" / "mapa-ufs.json"

# código do IBGE → sigla (minúscula, como no resto do painel)
SIGLAS = {
    "11": "ro", "12": "ac", "13": "am", "14": "rr", "15": "pa", "16": "ap", "17": "to",
    "21": "ma", "22": "pi", "23": "ce", "24": "rn", "25": "pb", "26": "pe", "27": "al", "28": "se", "29": "ba",
    "31": "mg", "32": "es", "33": "rj", "35": "sp", "41": "pr", "42": "sc", "43": "rs",
    "50": "ms", "51": "mt", "52": "go", "53": "df",
}
# UFs pequenas demais para o rótulo caber dentro quando o mapa é reduzido: ganham uma "chamada" (etiqueta ao lado)
COM_CHAMADA = ("rn", "pb", "pe", "al", "se", "es", "rj", "sc", "df")

LARGURA = 1000.0          # largura da tela do desenho, em unidades
MARGEM = 3                # folga para o traço da borda não ser cortado
TOLERANCIA = 0.9          # simplificação (Douglas–Peucker), em unidades ≈ 4 km
AREA_MINIMA = 1.5         # ilhotas com menos que isto (unidades²) somem na escala do painel
PROPORCAO_ROTULO = 1.6    # largura / altura da caixa de um rótulo de duas letras
LON_PONTA_LESTE = -34.7   # polígonos inteiros a leste daqui são ilhas oceânicas (Noronha, Trindade): fora do desenho

Ponto = tuple[float, float]


# ---- projeção ---------------------------------------------------------------------------------------------
class Albers:
    """Cônica equivalente de Albers (esfera), paralelos padrão 2°S e 22°S, meridiano central 54°O."""

    def __init__(self, lat1=-2.0, lat2=-22.0, lat0=-12.0, lon0=-54.0):
        r1, r2, r0 = map(math.radians, (lat1, lat2, lat0))
        self.lon0 = math.radians(lon0)
        self.n = (math.sin(r1) + math.sin(r2)) / 2
        self.c = math.cos(r1) ** 2 + 2 * self.n * math.sin(r1)
        self.rho0 = math.sqrt(self.c - 2 * self.n * math.sin(r0)) / self.n

    def __call__(self, lon: float, lat: float) -> Ponto:
        rho = math.sqrt(self.c - 2 * self.n * math.sin(math.radians(lat))) / self.n
        theta = self.n * (math.radians(lon) - self.lon0)
        return rho * math.sin(theta), self.rho0 - rho * math.cos(theta)


# ---- geometria ----------------------------------------------------------------------------------------------
def area_assinada(anel: list[Ponto]) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(anel, anel[1:] + anel[:1])) / 2


def douglas_peucker(pts: list[Ponto], eps: float) -> list[Ponto]:
    """Simplifica uma polilinha mantendo os dois extremos. Iterativo (os arcos podem ter milhares de vértices)."""
    n = len(pts)
    if n < 3:
        return list(pts)
    manter = [False] * n
    manter[0] = manter[-1] = True
    pilha = [(0, n - 1)]
    while pilha:
        i, j = pilha.pop()
        ax, ay = pts[i]
        dx, dy = pts[j][0] - ax, pts[j][1] - ay
        den = math.hypot(dx, dy)
        pior, onde = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            d = math.hypot(px - ax, py - ay) if den == 0 else abs(dx * (ay - py) - (ax - px) * dy) / den
            if d > pior:
                pior, onde = d, k
        if pior > eps:
            manter[onde] = True
            pilha += [(i, onde), (onde, j)]
    return [p for p, m in zip(pts, manter) if m]


def simplificar_aneis(aneis: dict[str, list[list[Ponto]]], eps: float) -> dict[str, list[list[Ponto]]]:
    """Simplifica todos os anéis por arcos (como o TopoJSON): fronteira compartilhada é simplificada uma vez só."""
    donos: dict[frozenset, set[str]] = {}
    for uf, lista in aneis.items():
        for anel in lista:
            for a, b in zip(anel, anel[1:] + anel[:1]):
                donos.setdefault(frozenset((a, b)), set()).add(uf)

    cache: dict[tuple, list[Ponto]] = {}

    def simplificado(arco: list[Ponto]) -> list[Ponto]:
        chave = min(tuple(arco), tuple(arco[::-1]))
        if chave not in cache:
            lista = list(chave)
            if lista[0] == lista[-1] and len(lista) > 3:  # laço fechado: divide no ponto mais distante
                meio = max(range(1, len(lista) - 1), key=lambda k: math.hypot(lista[k][0] - lista[0][0], lista[k][1] - lista[0][1]))
                cache[chave] = douglas_peucker(lista[: meio + 1], eps)[:-1] + douglas_peucker(lista[meio:], eps)
            else:
                cache[chave] = douglas_peucker(lista, eps)
        saida = cache[chave]
        return saida if tuple(arco) == chave else saida[::-1]

    resultado: dict[str, list[list[Ponto]]] = {}
    for uf, lista in aneis.items():
        novos = []
        for anel in lista:
            m = len(anel)
            donos_aresta = [frozenset(donos[frozenset((anel[i], anel[(i + 1) % m]))]) for i in range(m)]
            juncoes = [i for i in range(m) if donos_aresta[i - 1] != donos_aresta[i]]
            if not juncoes:  # ilha ou enclave sem vizinho: um arco só, fechado
                novo = simplificado(anel + [anel[0]])[:-1]
            else:
                novo = []
                for a, b in zip(juncoes, juncoes[1:] + [juncoes[0] + m]):
                    arco = [anel[i % m] for i in range(a, b + 1)]
                    novo += simplificado(arco)[:-1]
            novos.append(novo)
        resultado[uf] = novos
    return resultado


def arredondar(anel: list[Ponto]) -> list[tuple[int, int]]:
    """Coordenadas inteiras; vértices repetidos em seguida (por causa do arredondamento) são descartados."""
    saida: list[tuple[int, int]] = []
    for x, y in anel:
        p = (round(x), round(y))
        if not saida or saida[-1] != p:
            saida.append(p)
    if len(saida) > 1 and saida[0] == saida[-1]:
        saida.pop()
    return saida


def caminho_svg(aneis: list[list[tuple[int, int]]]) -> str:
    """`M x y l dx dy …z` por anel: relativo e sem separador antes de número negativo (mais curto)."""
    partes = []
    for anel in aneis:
        x0, y0 = anel[0]
        deltas = []
        for (xa, ya), (xb, yb) in zip(anel, anel[1:]):
            deltas += [xb - xa, yb - ya]
        texto = ""
        for v in deltas:
            s = str(v)
            texto += s if (not texto or s.startswith("-")) else " " + s
        partes.append(f"M{x0} {y0}l{texto}z")
    return "".join(partes)


# ---- onde cabe o rótulo ---------------------------------------------------------------------------------------
def pintar(aneis: list[list[tuple[int, int]]], dono: bytearray, largura: int, altura: int, indice: int) -> None:
    """Preenche no raster as células cujo centro está dentro dos anéis da UF (regra par-ímpar, varredura por linhas)."""
    arestas = [(a, b) for anel in aneis for a, b in zip(anel, anel[1:] + anel[:1]) if a[1] != b[1]]
    if not arestas:
        return
    for y in range(max(0, min(p[1] for anel in aneis for p in anel)), min(altura, max(p[1] for anel in aneis for p in anel) + 1)):
        yc = y + 0.5
        xs = sorted(
            a[0] + (yc - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            for a, b in arestas if min(a[1], b[1]) <= yc < max(a[1], b[1])
        )
        for xa, xb in zip(xs[0::2], xs[1::2]):
            for x in range(max(0, math.ceil(xa - 0.5)), min(largura, math.floor(xb - 0.5) + 1)):
                dono[y * largura + x] = indice


def melhor_posicao_do_rotulo(dono: bytearray, largura: int, altura: int, indice: int) -> dict | None:
    """Centro e largura da maior caixa (proporção PROPORCAO_ROTULO) que cabe inteira nas células da UF."""
    # corridas contínuas por linha: para cada célula, onde a corrida dela começa e termina
    inicio: dict[int, dict[int, int]] = {}
    fim: dict[int, dict[int, int]] = {}
    ys = []
    for y in range(altura):
        linha = dono[y * largura:(y + 1) * largura]
        if indice not in linha:
            continue
        ys.append(y)
        ini, fi = {}, {}
        x = 0
        while x < largura:
            if linha[x] == indice:
                x2 = x
                while x2 + 1 < largura and linha[x2 + 1] == indice:
                    x2 += 1
                for k in range(x, x2 + 1):
                    ini[k], fi[k] = x, x2
                x = x2 + 1
            else:
                x += 1
        inicio[y], fim[y] = ini, fi
    if not ys:
        return None
    celulas = [(x, y) for y in ys for x in inicio[y]]
    cx_med = sum(c[0] for c in celulas) / len(celulas) + 0.5
    cy_med = sum(c[1] for c in celulas) / len(celulas) + 0.5
    passo = 1 if len(celulas) < 4000 else 2 if len(celulas) < 30000 else 4  # UFs grandes toleram uma grade mais larga

    def caber(cx: int, cy: int) -> float:
        """Largura máxima de caixa centrada na célula (cx, cy); busca binária, pois a janela cresce com a largura."""
        meia = lambda y: min(cx + 0.5 - inicio[y][cx], fim[y][cx] + 1 - (cx + 0.5)) if cx in inicio.get(y, ()) else 0.0
        if meia(cy) <= 0:
            return 0.0
        baixo, alto = 0.0, 2 * meia(cy)
        for _ in range(9):
            w = (baixo + alto) / 2
            meia_altura = w / (2 * PROPORCAO_ROTULO)
            topo = math.floor(cy + 0.5 - meia_altura)
            base = math.floor(cy + 0.5 + meia_altura - 1e-9)
            if 2 * min(meia(y) for y in range(topo, base + 1)) >= w:
                baixo = w
            else:
                alto = w
        return baixo

    candidatos = []
    for x, y in celulas:
        if x % passo == 0 and y % passo == 0:
            w = caber(x, y)
            if w > 0:
                candidatos.append((w, x + 0.5, y + 0.5))
    maior = max(c[0] for c in candidatos)
    perto = [c for c in candidatos if c[0] >= 0.92 * maior]
    w, x, y = min(perto, key=lambda c: math.hypot(c[1] - cx_med, c[2] - cy_med))
    linha = int(y)
    leste = max(fim[linha].values()) + 1 if linha in fim else int(x)
    return {"x": round(x), "y": round(y), "lw": int(w), "e": int(leste)}


# ---- montagem ---------------------------------------------------------------------------------------------------
def poligonos(feature: dict) -> list[list[list[float]]]:
    g = feature["geometry"]
    return [p[0] for p in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]])]  # só o anel externo


def gerar(geojson: dict, tolerancia: float = TOLERANCIA) -> dict:
    proj = Albers()
    projetados: dict[str, list[list[Ponto]]] = {}
    for feat in geojson["features"]:
        uf = SIGLAS.get(str(feat["properties"]["codarea"]))
        if uf is None:
            continue
        for anel in poligonos(feat):
            if min(lon for lon, _ in anel) > LON_PONTA_LESTE:
                continue  # ilha oceânica
            pts = [proj(lon, lat) for lon, lat in anel]
            if pts[0] == pts[-1]:
                pts.pop()
            projetados.setdefault(uf, []).append(pts)

    faltam = sorted(set(SIGLAS.values()) - set(projetados))
    if faltam:
        raise ValueError(f"UFs ausentes na malha: {faltam}")

    xs = [x for lista in projetados.values() for anel in lista for x, _ in anel]
    ys = [y for lista in projetados.values() for anel in lista for _, y in anel]
    escala = LARGURA / (max(xs) - min(xs))
    # SVG cresce para baixo: inverte o y; a origem passa a ser o canto superior esquerdo + margem
    normalizados = {
        uf: [[((x - min(xs)) * escala + MARGEM, (max(ys) - y) * escala + MARGEM) for x, y in anel] for anel in lista]
        for uf, lista in projetados.items()
    }
    simples = simplificar_aneis(normalizados, tolerancia)

    aneis_finais: dict[str, list[list[tuple[int, int]]]] = {}
    for uf, lista in simples.items():
        finais = [a for a in (arredondar(anel) for anel in lista) if len(a) >= 3 and abs(area_assinada(a)) >= AREA_MINIMA]
        if not finais:  # nunca deixar uma UF sem forma
            finais = [max((arredondar(anel) for anel in lista), key=lambda a: abs(area_assinada(a)))]
        aneis_finais[uf] = finais

    largura = math.ceil(max(x for lista in aneis_finais.values() for a in lista for x, _ in a)) + MARGEM
    altura = math.ceil(max(y for lista in aneis_finais.values() for a in lista for _, y in a)) + MARGEM
    area = {uf: sum(abs(area_assinada(a)) for a in lista) for uf, lista in aneis_finais.items()}

    ordem = sorted(aneis_finais)
    dono = bytearray([255]) * (largura * altura)
    for i, uf in enumerate(ordem):
        pintar(aneis_finais[uf], dono, largura, altura, i)

    ufs = []
    for uf in sorted(aneis_finais, key=lambda u: sem_acento(UF_NOMES[u])):  # ordem alfabética: é a ordem do Tab no mapa
        item = {"uf": uf, "nome": UF_NOMES[uf], "d": caminho_svg(aneis_finais[uf]), "area": round(area[uf])}
        item.update(melhor_posicao_do_rotulo(dono, largura, altura, ordem.index(uf)) or {})
        if uf in COM_CHAMADA:
            item["chamada"] = True
        ufs.append(item)
    return {
        "fonte": "IBGE, Malhas Territoriais (UFs); projeção cônica equivalente de Albers, simplificada",
        "largura": largura, "altura": altura, "ufs": ufs,
    }


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)).casefold()


def baixar(qualidade: str = "intermediaria") -> dict:
    import requests  # só aqui: o painel em si não precisa dele para isto

    resp = requests.get(
        IBGE_URL.format(qualidade=qualidade), timeout=120,
        headers={"User-Agent": "eleicoes-ao-vivo (gerador de mapa; uso unico)"},  # cabeçalho HTTP: só ASCII
    )
    resp.raise_for_status()
    return resp.json()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--entrada", type=Path, help="GeoJSON das UFs já baixado (senão, baixa do IBGE)")
    ap.add_argument("--saida", type=Path, default=DESTINO)
    ap.add_argument("--qualidade", default="intermediaria", choices=["minima", "intermediaria", "maxima"])
    ap.add_argument("--tolerancia", type=float, default=TOLERANCIA)
    args = ap.parse_args(argv)

    geojson = json.loads(args.entrada.read_text(encoding="utf-8")) if args.entrada else baixar(args.qualidade)
    mapa = gerar(geojson, args.tolerancia)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(mapa, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    tamanho = args.saida.stat().st_size
    print(f"{args.saida}: {len(mapa['ufs'])} UFs, {mapa['largura']}x{mapa['altura']}, {tamanho / 1024:.1f} KB", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
