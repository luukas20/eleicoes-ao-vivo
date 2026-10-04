"""Cores dos partidos, usadas para pintar os candidatos (barras, mapa, gráfico).

Cada partido tem o tom da sua marca (vermelho do PT, azul do PL, laranja do NOVO...), recalibrado para
a tela: saturação e luminosidade equilibradas entre si, uma versão para o fundo claro e outra para o escuro.
Os valores foram desenhados em OKLCH e conferidos quanto a contraste do texto sobre o preenchimento
(WCAG 4,5:1), visibilidade da marca sobre o fundo escuro e separação para quem tem daltonismo; o que
sobra de ambiguidade (siglas de cor parecida na mesma disputa) é resolvido em `cores.atribuir`.

Cada entrada: sigla -> (claro, escuro, alternativa clara, alternativa escura). A alternativa é a mesma
família de cor bem mais clara ou mais escura; só é usada quando outro candidato da mesma disputa já
ocupa uma cor parecida. `RESERVA` cobre partidos desconhecidos (siglas que o TSE criar depois).
"""
from __future__ import annotations

import re
import unicodedata
import zlib

PARTIDOS: dict[str, tuple[str, str, str, str]] = {
    # vermelhos
    "PT": ("#DD0E34", "#F83D60", "#FF8482", "#C6003E"),
    "PCdoB": ("#9E122F", "#E74258", "#D55C65", "#C3163C"),
    "PSTU": ("#E95048", "#FF887C", "#A70311", "#CF3E38"),
    "PCB": ("#AB3B2D", "#D06151", "#E27868", "#AB3F31"),
    "PCO": ("#78172D", "#CA445B", "#AE545F", "#FF8795"),
    "UP": ("#2D2D34", "#D0D0D7", "#5D5D64", "#97979E"),
    # rosas e roxos
    "Cidadania": ("#F93497", "#FF82B4", "#A90161", "#D8137F"),
    "Democrata": ("#A4345B", "#CA5C7E", "#DB7290", "#A73C5F"),
    "MOBILIZA": ("#E1909F", "#E1909F", "#A65A69", "#A65A69"),
    "PSOL": ("#8B34C5", "#AD5EE8", "#C077F9", "#8B3AC3"),
    # laranjas e amarelos
    "PDT": ("#FC8F6E", "#FC8F6E", "#BC5636", "#BC5636"),
    "NOVO": ("#F36801", "#FE913E", "#A04303", "#B55B03"),
    "Solidariedade": ("#FE9D38", "#FE9D38", "#BD6D05", "#BD6D05"),
    "PSD": ("#F7B828", "#F7B828", "#B38309", "#B38309"),
    "MISSÃO": ("#B6A643", "#C2B356", "#7E6F01", "#90811D"),
    "PSB": ("#F5EB3D", "#F5EB3D", "#BBA604", "#BBA604"),
    "DC": ("#A97D3A", "#CCA162", "#6F4A01", "#936A29"),
    # verdes
    "PODE": ("#1CDA73", "#1CDA73", "#08994E", "#08994E"),
    "MDB": ("#09BE8A", "#2CCE99", "#067F5C", "#059269"),
    "PRD": ("#339249", "#5CB36C", "#77C984", "#1E7B37"),
    "PV": ("#146D34", "#428F56", "#5BA26B", "#81C590"),
    "REDE": ("#6FC9A8", "#6FC9A8", "#329072", "#329072"),
    # azuis
    "Avante": ("#099BA5", "#35C1CD", "#026168", "#03818A"),
    "UNIÃO": ("#36BAEB", "#36BAEB", "#017EA4", "#017EA4"),
    "PP": ("#8FCDF5", "#8FCDF5", "#5894BA", "#5894BA"),
    "Republicanos": ("#0271B1", "#2995DE", "#4CA9EF", "#0067A1"),
    "PSDB": ("#1D85E5", "#5CAAFE", "#86BFFF", "#0071CB"),
    "PL": ("#2D49C9", "#486AE7", "#6086FC", "#8BAAFE"),
    "Agir": ("#1D3983", "#4A70CD", "#506FB6", "#84AAFE"),
    "PRTB": ("#1161BB", "#3F85DF", "#599AEF", "#90BFFF"),
}

# sigla -> chave de cor, para siglas antigas ou grafias diferentes que o feed possa trazer
APELIDOS = {
    "PODEMOS": "PODE", "PMN": "MOBILIZA", "PMB": "Democrata", "PTC": "Agir", "PPS": "Cidadania", "PRB": "Republicanos",
    "DEM": "UNIÃO", "PSL": "UNIÃO", "PTB": "PRD", "PATRIOTA": "PRD", "PROS": "Solidariedade", "SD": "Solidariedade",
    "PHS": "PODE", "PSC": "PODE", "PR": "PL",
}

# cores de reserva (partidos desconhecidos, ou todas as variantes de um partido já ocupadas): claro, escuro
RESERVA: dict[str, tuple[str, str]] = {
    "r1": ("#7089A4", "#93ACC7"),
    "r2": ("#8D9A59", "#ACB979"),
    "r3": ("#985B93", "#BC7EB6"),
    "r4": ("#B17652", "#D59A76"),
    "r5": ("#488C94", "#6FB0B7"),
    "r6": ("#C3AF86", "#C3AF86"),
}
NEUTRO = ("#B8B2A3", "#5C5F6B")  # "outros" / sem cor definida

# Quem mantém a cor própria quando duas siglas de cor parecida disputam a mesma eleição: o mais "conhecido" primeiro.
PRIORIDADE = (
    "PT", "PL", "PSD", "MDB", "UNIÃO", "PP", "Republicanos", "PSB", "PDT", "PSDB", "NOVO", "PODE", "PSOL", "PCdoB", "PV",
    "REDE", "Cidadania", "Solidariedade", "Avante", "PRD", "Agir", "MISSÃO", "DC", "MOBILIZA", "Democrata", "PRTB", "UP",
    "PSTU", "PCB", "PCO",
)


def _sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _forma(texto: str) -> str:
    """Forma comparável de uma sigla: sem acentos, maiúscula, sem pontuação ("PC do B" e "PCdoB" viram "PCDOB")."""
    return re.sub(r"[^A-Z0-9]", "", _sem_acentos(texto).upper())


_POR_FORMA = {_forma(sigla): sigla for sigla in PARTIDOS}
_POR_FORMA.update({_forma(apelido): alvo for apelido, alvo in APELIDOS.items()})


def partido_de(sigla: str) -> str | None:
    """Sigla canônica do partido (chave de `PARTIDOS`), ou None se o painel não conhece essa sigla."""
    return _POR_FORMA.get(_forma(sigla or ""))


def chave_de(sigla: str, alternativa: bool = False) -> str | None:
    """Chave de cor ("pt", "pt-alt"...) usada no CSS (`data-cor`) para uma sigla, ou None se desconhecida."""
    partido = partido_de(sigla)
    if partido is None:
        return None
    return _chave(partido) + ("-alt" if alternativa else "")


def partido_representante(composicao: str) -> str | None:
    """Partido que dá a cor a uma federação ou coligação: entre os componentes ("PT/PC do B/PV", "PP / UNIÃO"), o de maior
    prioridade (`PRIORIDADE`). None se nenhum componente é conhecido."""
    conhecidos = [p for p in (partido_de(parte) for parte in re.split(r"[/,]", composicao or "")) if p]
    return min(conhecidos, key=PRIORIDADE.index) if conhecidos else None


def chave_do_agrupamento(composicao: str, sigla: str | None = None) -> str:
    """Cor estável de um agrupamento (partido isolado, federação ou coligação) nas disputas proporcionais."""
    representante = sigla if (sigla and partido_de(sigla)) else partido_representante(composicao)
    return chave_do_partido(representante) if representante else (chave_do_partido(sigla) if sigla else "neutro")


def chave_do_partido(sigla: str) -> str:
    """Cor estável de um partido, sem tratar colisões: a própria cor ou, para siglas que o painel não conhece, uma de
    reserva escolhida pela sigla. Usada nas visões que cruzam UFs (mapa e tabelas de Governador e Senador), em que o
    mesmo partido precisa ter a mesma cor em todas as linhas."""
    chave = chave_de(sigla)
    if chave:
        return chave
    forma = _forma(sigla or "")
    return list(RESERVA)[zlib.crc32(forma.encode()) % len(RESERVA)] if forma else "neutro"


def _chave(sigla_canonica: str) -> str:
    return _forma(sigla_canonica).lower()


def hex_claro(chave: str) -> str | None:
    """Cor (modo claro) de uma chave de cor; None se a chave não existe."""
    if chave in RESERVA:
        return RESERVA[chave][0]
    if chave == "neutro":
        return NEUTRO[0]
    alternativa = chave.endswith("-alt")
    base = chave[:-4] if alternativa else chave
    for sigla, cores in PARTIDOS.items():
        if _chave(sigla) == base:
            return cores[2] if alternativa else cores[0]
    return None


def todas_as_chaves() -> dict[str, tuple[str, str]]:
    """{chave: (claro, escuro)} de todas as cores que podem aparecer na interface (inclui alternativas, reserva e neutro)."""
    saida: dict[str, tuple[str, str]] = {}
    for sigla, (claro, escuro, alt_claro, alt_escuro) in PARTIDOS.items():
        saida[_chave(sigla)] = (claro, escuro)
        saida[_chave(sigla) + "-alt"] = (alt_claro, alt_escuro)
    saida.update(RESERVA)
    saida["neutro"] = NEUTRO
    return saida
