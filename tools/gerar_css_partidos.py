"""Gera `app/static/css/partidos.css` (as cores dos partidos como variáveis CSS) a partir de `app/partidos.py`.

    python -m tools.gerar_css_partidos            # reescreve o arquivo
    python -m tools.gerar_css_partidos --conferir # só confere se está em dia (sai com 1 se não estiver)

Cada cor vira duas variáveis por tema (`--c-<chave>` e `--o-<chave>`: a cor e a tinta do texto que vai por cima,
escolhida pelo melhor contraste) e uma regra `[data-cor="<chave>"]` que as aplica como `--cor` e `--sobre`.
O front-end só escreve `data-cor="pt"` nos elementos; o tema claro/escuro troca os valores sozinho.
"""
from __future__ import annotations

import sys
from pathlib import Path

from app import partidos

DESTINO = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "partidos.css"
BRANCO = "#FFFFFF"
TINTA = "#16141C"  # igual a --tinta (modo claro) do app.css: o texto escuro que vai sobre cores claras


def _luminancia(hexa: str) -> float:
    canais = []
    for i in (1, 3, 5):
        v = int(hexa[i:i + 2], 16) / 255
        canais.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def contraste(a: str, b: str) -> float:
    claro, escuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def tinta_sobre(fundo: str) -> str:
    """Branco ou tinta escura, o que tiver mais contraste sobre `fundo`."""
    return BRANCO if contraste(fundo, BRANCO) >= contraste(fundo, TINTA) else TINTA


def css() -> str:
    cores = partidos.todas_as_chaves()

    def variaveis(indice: int) -> str:
        return "\n".join(f"  --c-{k}: {v[indice]}; --o-{k}: {tinta_sobre(v[indice])};" for k, v in cores.items())

    regras = "\n".join(f'[data-cor="{k}"] {{ --cor: var(--c-{k}); --sobre: var(--o-{k}); }}' for k in cores)
    return (
        "/* Cores dos partidos. GERADO por tools/gerar_css_partidos.py a partir de app/partidos.py: não edite à mão. */\n"
        f":root {{\n{variaveis(0)}\n}}\n"
        "@media (prefers-color-scheme: dark) {\n"
        f'  :root:where(:not([data-tema="claro"])) {{\n{variaveis(1)}\n  }}\n'
        "}\n"
        f':root[data-tema="escuro"] {{\n{variaveis(1)}\n}}\n'
        f"{regras}\n"
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    novo = css()
    if "--conferir" in argv:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if atual != novo:
            print(f"{DESTINO} está desatualizado: rode  python -m tools.gerar_css_partidos")
            return 1
        return 0
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(novo, encoding="utf-8", newline="\n")
    print(f"escrito {DESTINO} ({len(novo)} bytes, {len(partidos.todas_as_chaves())} cores)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
