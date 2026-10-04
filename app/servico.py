"""Modelo de leitura: monta, a partir dos arquivos já interpretados no Store, o que a interface consome.

Regras importantes:
* os payloads de dados só contêm o que muda quando o TSE publica algo novo, para o ETag ficar
  estável e o navegador receber 304 entre uma totalização e outra; o que é volátil (idade da última
  confirmação) sai em `frescor()` e viaja em cabeçalhos HTTP;
* os valores do TSE são repassados como publicados (percentuais em `pct.t`); derivados do painel,
  como a diferença entre o 1º e o 2º, ficam em campos próprios e são rotulados na tela.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from .catalog import Alvo, Disputa, disputas_ativas
from .config import Settings
from .cores import NEUTRO, atribuir
from .partidos import chave_do_agrupamento, chave_do_partido, partido_representante
from .historico import Historico, amostrar
from .store import Snapshot, Store, chave
from .tse.dominio import BRASIL, CARGO_POR_SLUG, UF_NOMES, UFS, nome_abrangencia
from .tse.parse import BRT, sem_acentos
from .tse.urls import TseUrls

CARGOS_DA_PAGINA_UF = ("presidente", "governador", "senador")
SLUGS_PROPORCIONAIS = ("deputado-federal", "deputado-estadual", "deputado-distrital")
DESTAQUES_POR_UF = 20  # candidatos mais votados que vão no painel da UF (uma página da busca); o resto vem pela busca
TTL_MUNICIPIO_S = 90.0  # um município é consultado ao TSE enquanto alguém o pedir a cada < 90 s


class NaoEncontrado(Exception):
    """UF ou município que não existe nos arquivos do TSE."""


class Indisponivel(Exception):
    """Ainda não dá para atender (lista de municípios não carregada ou limite de acompanhamentos atingido)."""


def _iso_epoch(epoch: float | None) -> str | None:
    return datetime.fromtimestamp(epoch, BRT).isoformat(timespec="seconds") if epoch else None


class Servico:
    def __init__(self, settings: Settings, store: Store, *, poller=None, historico: Historico | None = None):
        self.cfg = settings
        self.store = store
        self.poller = poller
        self.historico = historico or Historico()
        self._cache_disputas: tuple[str, list[Disputa]] = ("", [])
        self._cache_municipios: tuple[tuple, dict] = ((), {})
        self._cache_agrupamentos: dict[str, tuple[dict, list]] = {}  # chave do arquivo -> (dados de que saiu, agrupamentos)
        self._fotos_validas: set[tuple[int, str, str]] = set()  # (eleição, escopo, sqcand) conhecidos
        store.ao_mudar(self._ao_mudar)

    # ---- reação a novos dados -----------------------------------------------------------------------
    def _ao_mudar(self, snap: Snapshot) -> None:
        if snap.tipo != "u":
            return
        r = snap.dados
        cargo, abr = r.get("cargo"), r["abrangencia"]
        if not cargo or abr["tipo"] == "mu":
            return
        escopo_foto = BRASIL if cargo["cd"] == 1 else abr["codigo"]
        ele = int(r["ele"])
        self._fotos_validas.update((ele, escopo_foto, c["sq"]) for c in r["candidatos"])
        if cargo["cd"] in (1, 3, 5):  # BR e UFs; municípios não têm histórico
            self.historico.registrar(snap.chave, r)

    def foto_valida(self, ele: int, escopo: str, sq: str) -> bool:
        """Só buscamos no TSE fotos de candidatos que aparecem nos arquivos (evita 404 em massa)."""
        return (ele, escopo, sq) in self._fotos_validas

    def urls(self, ele: int) -> TseUrls | None:
        d = next((d for d in self.disputas() if int(d.ele) == ele), None)
        cfg = self.store.get("cfg")
        if d is None or cfg is None:
            return None
        return TseUrls(self.cfg.tse_base, self.cfg.ambiente, d.ciclo, cfg.dados.get("dirs"))

    # ---- catálogo ------------------------------------------------------------------------------------
    def disputas(self) -> list[Disputa]:
        snap = self.store.get("cfg")
        if snap is None:
            return []
        if self._cache_disputas[0] != snap.idg:
            self._cache_disputas = (snap.idg, disputas_ativas(snap.dados, so=self.cfg.eleicoes, cargos=self.cfg.cargos))
        return self._cache_disputas[1]

    def turnos(self) -> list[int]:
        return sorted({d.turno for d in self.disputas()})

    def _iniciou(self, ele: str) -> bool:
        return any(s.dados["secoes"].get("st", 0) > 0 for s in self.store.itens(f"u:{int(ele)}:"))

    def turno_padrao(self) -> int:
        """O maior turno cuja apuração já começou; antes disso, o primeiro."""
        turnos = self.turnos()
        for t in sorted(turnos, reverse=True):
            if t != turnos[0] and any(self._iniciou(d.ele) for d in self.disputas() if d.turno == t):
                return t
        return turnos[0] if turnos else 1

    def disputa(self, slug: str, turno: int | None = None) -> Disputa | None:
        cargo = CARGO_POR_SLUG.get(slug)
        if cargo is None:
            return None
        do_cargo = [d for d in self.disputas() if d.cargo.cd == cargo.cd]
        achada = next((d for d in do_cargo if d.turno == (turno or self.turno_padrao())), None)
        if achada is None and turno is None and do_cargo:
            # Senador e deputados só têm 1º turno: quando o 2º começa e vira o padrão, eles continuam valendo (o 1º é o único que existe)
            achada = max(do_cargo, key=lambda d: d.turno)
        return achada

    def turnos_do_cargo(self, cargo: int) -> list[int]:
        """Turnos em que o cargo é votado (Senador e deputados: só o 1º): é o que a página do cargo oferece para escolher."""
        return sorted({d.turno for d in self.disputas() if d.cargo.cd == cargo})

    # ---- peças ---------------------------------------------------------------------------------------
    @staticmethod
    def _candidato(c: dict, ele: str, escopo_foto: str, cores: dict[str, str]) -> dict:
        return {**c, "cor": cores.get(c["sq"], NEUTRO), "foto": f"/foto/{int(ele)}/{escopo_foto}/{c['sq']}"}

    @staticmethod
    def _resumo(c: dict | None, cores: dict[str, str]) -> dict | None:
        if c is None:
            return None
        # `cor`: a da disputa nesta UF (pode ser a variante do partido); `cor_partido`: a do partido, igual em todas as UFs
        return {k: c[k] for k in ("sq", "numero", "urna", "partido", "votos", "pct", "eleito")} | {
            "cor": cores.get(c["sq"], NEUTRO), "cor_partido": chave_do_partido(c["partido"])}

    def _resultado(self, snap: Snapshot, d: Disputa, uf: str, nome_local: str | None = None) -> dict[str, Any]:
        r = snap.dados
        escopo_foto = BRASIL if d.cargo.cd == 1 else uf
        cores = atribuir(r["candidatos"])
        return {
            "ele": r["ele"], "turno": r["turno"], "fase": r["fase"], "idg": r["idg"],
            "gerado_em": r["gerado_em"], "totalizado_em": r["totalizado_em"],
            "abrangencia": {**r["abrangencia"], "nome": nome_local or nome_abrangencia(r["abrangencia"]["codigo"])},
            "cargo": r["cargo"], "estado": r["estado"],
            "secoes": r["secoes"], "eleitorado": r["eleitorado"], "votos": r["votos"],
            "candidatos": [self._candidato(c, d.ele, escopo_foto, cores) for c in r["candidatos"]],
        }

    def _linha_uf(self, d: Disputa, uf: str) -> dict[str, Any]:
        snap = self.store.get(chave("u", d.ele, d.cargo.cd, uf))
        base = {"codigo": uf, "nome": nome_abrangencia(uf)}
        if snap is None:
            return {**base, "disponivel": False}
        r = snap.dados
        cores = atribuir(r["candidatos"])
        vagas = (r["cargo"] or {}).get("vagas") or 1
        com_votos = [c for c in r["candidatos"] if c["votos"] > 0]
        top = [self._resumo(c, cores) for c in com_votos[: max(2, vagas + 1)]]
        # margem = distância entre quem ocupa a última vaga e o primeiro colocado fora das vagas
        # (1º x 2º com uma vaga; 2º x 3º no Senado, que elege dois por UF). Cálculo do painel.
        margem = None
        if len(com_votos) > vagas:
            margem = round(com_votos[vagas - 1]["pct"]["n"] - com_votos[vagas]["pct"]["n"], 2)
        return {
            **base, "disponivel": True,
            "andamento": r["estado"]["andamento"], "divulga": r["estado"]["divulga"],
            "definido": r["estado"]["definido"], "final": r["estado"]["totalizacao_final"],
            "totalizado_em": r["totalizado_em"],
            "secoes": {k: r["secoes"].get(k) for k in ("ts", "st", "pst")},
            "vagas": vagas, "top": top, "margem_pp": margem,
        }

    def _legenda(self, d: Disputa) -> list[dict]:
        snap = self.store.get(chave("u", d.ele, d.cargo.cd, BRASIL))
        if snap is None:
            return []
        cores = atribuir(snap.dados["candidatos"])
        return [  # só quem já tem votos, na ordem do ranking (o resto não aparece no mapa)
            {"sq": c["sq"], "cor": cores.get(c["sq"], NEUTRO), "urna": c["urna"], "numero": c["numero"], "partido": c["partido"]}
            for c in snap.dados["candidatos"] if c["votos"] > 0
        ]

    # ---- respostas da API -------------------------------------------------------------------------------
    def meta(self) -> dict[str, Any]:
        cfg = self.store.get("cfg")
        vistos: set[str] = set()
        cargos = []
        for d in self.disputas():
            if d.cargo.slug not in vistos:
                vistos.add(d.cargo.slug)
                cargos.append({"slug": d.cargo.slug, "nome": d.cargo.nome, "tipo": d.cargo.tipo})
        primeira = self.disputas()[0] if self.disputas() else None
        return {
            "fase": cfg.dados["fase"] if cfg else None,
            "data": primeira.data if primeira else None,
            "turnos": self.turnos(), "turno_padrao": self.turno_padrao(),
            "cargos": cargos,
            "ufs": [{"codigo": u, "nome": UF_NOMES[u]} for u in UFS],
            "frescor": self.frescor(),
        }

    def painel_presidente(self, turno: int | None = None) -> dict[str, Any] | None:
        d = self.disputa("presidente", turno)
        if d is None:
            return None
        snap = self.store.get(chave("u", d.ele, 1, BRASIL))
        saida: dict[str, Any] = {"turno": d.turno, "ele": d.ele, "turnos": self.turnos(), "disponivel": snap is not None}
        if snap is None:
            return saida
        saida["resultado"] = self._resultado(snap, d, BRASIL)
        saida["ufs"] = [self._linha_uf(d, uf) for uf in d.ufs]
        saida["legenda"] = self._legenda(d)
        ab = self.store.get(chave("ab", d.ele, abr=BRASIL))
        if ab:
            br = next((a for a in ab.dados["abrangencias"] if a["tipo"] == "br"), None)
            if br:
                saida["ufs_andamento"] = br["contagem"]
        return saida

    def tabela_cargo(self, slug: str, turno: int | None = None) -> dict[str, Any] | None:
        d = self.disputa(slug, turno)
        if d is None:
            return None
        return {
            "slug": slug, "nome": d.cargo.nome, "turno": d.turno, "ele": d.ele, "turnos": self.turnos_do_cargo(d.cargo.cd),
            "vagas": 2 if d.cargo.cd == 5 else 1,
            "linhas": [self._linha_uf(d, uf) for uf in d.ufs],
        }

    def pagina_uf(self, uf: str, turno: int | None = None) -> dict[str, Any] | None:
        uf = uf.lower()
        if uf not in UF_NOMES or uf == "zz":
            return None
        turno = turno or self.turno_padrao()
        disputas_uf = []
        for slug in CARGOS_DA_PAGINA_UF:
            d = self.disputa(slug, turno)
            if d is None or uf not in d.ufs:
                continue
            snap = self.store.get(chave("u", d.ele, d.cargo.cd, uf))
            disputas_uf.append({
                "slug": slug, "nome": d.cargo.nome, "ele": d.ele, "turno": d.turno,
                "disponivel": snap is not None, "resultado": self._resultado(snap, d, uf) if snap else None,
            })
        proporcionais = [
            {"slug": d.cargo.slug, "nome": d.cargo.nome}
            for d in self.disputas() if d.cargo.tipo == "proporcional" and d.turno == turno and uf in d.ufs
        ]
        return {"uf": uf, "nome": UF_NOMES[uf], "turno": turno, "turnos": self.turnos(), "disputas": disputas_uf, "proporcionais": proporcionais}

    # ---- evolução ao longo da apuração ---------------------------------------------------------------------------
    def evolucao(self, slug: str, abr: str, turno: int | None = None, n: int = 3) -> dict[str, Any]:
        """Percentual dos `n` primeiros colocados a cada totalização registrada (os do último ponto)."""
        d = self.disputa(slug, turno)
        abr = abr.lower()
        if d is None or (abr == BRASIL and not d.nacional) or (abr != BRASIL and abr not in d.ufs):
            raise NaoEncontrado("disputa ou abrangência sem histórico")
        k = chave("u", d.ele, d.cargo.cd, abr)
        pontos = self.historico.serie(k)
        saida: dict[str, Any] = {
            "slug": slug, "nome": d.cargo.nome, "abr": abr, "turno": d.turno, "ele": d.ele, "n": n,
            "total_pontos": len(pontos), "desde": pontos[0]["t"] if pontos else None, "pontos": [], "series": [],
        }
        if not pontos:
            return saida
        amostra = amostrar(pontos, 600)
        saida["pontos"] = [{"t": p["t"], "st": p["st"], "pst": p["pst"]} for p in amostra]
        snap = self.store.get(k)
        nomes = {c["sq"]: c for c in snap.dados["candidatos"]} if snap else {}
        ultimo = pontos[-1]["c"]
        lideres = sorted(ultimo, key=lambda sq: -ultimo[sq][0])[:n]
        cores = atribuir(snap.dados["candidatos"]) if snap else {}
        for sq in lideres:
            c = nomes.get(sq, {})
            saida["series"].append({
                "sq": sq, "urna": c.get("urna", sq), "numero": c.get("numero", ""), "partido": c.get("partido", ""),
                "cor": cores.get(sq, NEUTRO),
                "pct": [p["c"].get(sq, [0, None])[1] if sq in p["c"] else None for p in amostra],
                "votos": [p["c"][sq][0] if sq in p["c"] else None for p in amostra],
            })
        return saida

    # ---- municípios -------------------------------------------------------------------------------------------
    def _municipios_por_uf(self) -> dict[str, dict[str, dict]]:
        """{uf: {código: município}} a partir do EA12 mais completo já carregado (o da eleição com mais UFs)."""
        melhor = None
        for s in self.store.itens("cm:"):
            if melhor is None or len(s.dados["ufs"]) > len(melhor.dados["ufs"]):
                melhor = s
        if melhor is None:
            return {}
        marca = (melhor.chave, melhor.conteudo_hash or melhor.idg)
        if self._cache_municipios[0] != marca:
            mapa = {uf: {m["cd"]: m for m in dados["municipios"]} for uf, dados in melhor.dados["ufs"].items()}
            self._cache_municipios = (marca, mapa)
        return self._cache_municipios[1]

    def buscar_municipios(self, uf: str, termo: str, limite: int = 20) -> list[dict[str, Any]]:
        """Municípios da UF cujo nome começa (primeiro) ou contém o termo, sem diferenciar acentos."""
        uf = uf.lower()
        mapa = self._municipios_por_uf()
        if not mapa:
            raise Indisponivel("a lista de municípios do TSE ainda não foi carregada")
        if uf not in mapa or uf == "zz":
            raise NaoEncontrado("UF desconhecida")
        busca = sem_acentos(termo.strip())
        todos = list(mapa[uf].values())
        if busca:
            achados = [m for m in todos if m["busca"].startswith(busca)] + [m for m in todos if busca in m["busca"] and not m["busca"].startswith(busca)]
        else:
            achados = [m for m in todos if m["capital"]]
        return [{"cd": m["cd"], "nome": m["nome"], "capital": m["capital"]} for m in achados[:limite]]

    def pagina_municipio(self, uf: str, codigo: str, turno: int | None = None) -> dict[str, Any]:
        """Presidente, Governador e Senador de um município. Pede ao poller para acompanhá-lo (sob demanda)."""
        uf = uf.lower()
        mapa = self._municipios_por_uf()
        if not mapa:
            raise Indisponivel("a lista de municípios do TSE ainda não foi carregada")
        municipio = mapa.get(uf, {}).get(str(codigo).zfill(5)) if uf != "zz" and str(codigo).isdigit() else None
        if municipio is None:  # só montamos URLs de municípios que o EA12 lista: nada de 404 em massa
            raise NaoEncontrado("município não encontrado nesta UF")
        turno = turno or self.turno_padrao()
        disputas, limite_atingido = [], False
        for slug in CARGOS_DA_PAGINA_UF:
            d = self.disputa(slug, turno)
            if d is None or uf not in d.ufs:
                continue
            chave_u = chave("u", d.ele, d.cargo.cd, uf, municipio["cd"])
            urls = self.urls(int(d.ele))
            if self.poller and urls:
                alvo = Alvo(chave_u, "u", urls.resultado(d.ele, d.cargo.cd, uf, municipio=municipio["cd"]), "sob_demanda",
                            {"ele": d.ele, "cargo": d.cargo.cd, "abr": uf, "mun": municipio["cd"]})
                if not self.poller.solicitar(alvo, TTL_MUNICIPIO_S):
                    limite_atingido = True
            snap = self.store.get(chave_u)
            disputas.append({
                "slug": slug, "nome": d.cargo.nome, "ele": d.ele, "turno": d.turno, "disponivel": snap is not None,
                "resultado": self._resultado(snap, d, uf, nome_local=municipio["nome"]) if snap else None,
            })
        if limite_atingido and not any(x["disponivel"] for x in disputas):
            raise Indisponivel("muitos municípios em acompanhamento neste momento; tente novamente em instantes")
        return {
            "uf": uf, "nome_uf": UF_NOMES[uf], "turno": turno, "turnos": self.turnos(),
            "municipio": {"cd": municipio["cd"], "nome": municipio["nome"], "capital": municipio["capital"], "zonas": len(municipio["zonas"])},
            "disputas": disputas,
        }

    # ---- cargos proporcionais (deputados) --------------------------------------------------------------------
    @staticmethod
    def _rotulo_composicao(composicao: str) -> str:
        """"PP / UNIÃO" -> "PP/UNIÃO"."""
        return "/".join(p.strip() for p in (composicao or "").split("/") if p.strip())

    def _agrupamentos(self, snap: Snapshot) -> list[dict[str, Any]]:
        """Partidos isolados e federações de uma UF, com votos, vagas (provisórias até a totalização final) e candidatos.

        Guardado por arquivo: a visão nacional pede os das 27 UFs a cada consulta, e eles só mudam quando o arquivo muda.
        """
        guardado = self._cache_agrupamentos.get(snap.chave)
        if guardado is not None and guardado[0] is snap.dados:
            return guardado[1]
        grupos = self._calcular_agrupamentos(snap.dados)
        self._cache_agrupamentos[snap.chave] = (snap.dados, grupos)
        return grupos

    def _calcular_agrupamentos(self, r: dict) -> list[dict[str, Any]]:
        por_agr: dict[str, list[dict]] = {}
        for c in r["candidatos"]:  # já em ordem de votos
            por_agr.setdefault(c["agr"], []).append(c)
        validos = (r["votos"] or {}).get("vv") or 0
        # a cor de cada agrupamento é a do partido que o representa; entre os agrupamentos da UF, as parecidas são separadas
        # (como nos candidatos). Quem está registrado não muda durante a apuração, então a cor também não.
        representantes = [
            {"sq": a["n"], "partido": partido_representante(a["composicao"]) or (a["partidos"][0]["sigla"] if a["partidos"] else a["nome"])}
            for a in r["agremiacoes"]
        ]
        cores_uf = atribuir(representantes)
        saida = []
        for a in r["agremiacoes"]:
            cands = por_agr.get(a["n"], [])
            isolado = a["tipo"] == "i"
            sigla = a["partidos"][0]["sigla"] if isolado and a["partidos"] else None
            primeiro = a["partidos"][0] if a["partidos"] else {}
            rotulo = sigla if isolado and sigla else self._rotulo_composicao(a["composicao"]) or a["nome"]
            mais = cands[0] if cands and cands[0]["votos"] > 0 else None
            saida.append({
                "id": a["n"], "tipo": a["tipo"], "nome": a["nome"], "rotulo": rotulo, "composicao": self._rotulo_composicao(a["composicao"]),
                "chave": f"f:{primeiro.get('federacao')}" if not isolado and primeiro.get("federacao") else f"p:{primeiro.get('n', a['n'])}",
                "cor": cores_uf.get(a["n"], NEUTRO), "cor_partido": chave_do_agrupamento(a["composicao"], sigla),
                "partidos": [{"sigla": p["sigla"], "numero": p["n"]} for p in a["partidos"]],
                "votos_nominais": a["votos_nominais"], "votos_legenda": a["votos_legenda"], "votos_total": a["votos_total"],
                "pct_validos": round(100 * a["votos_total"] / validos, 2) if validos else None,  # cálculo do painel
                "vagas": a["vagas"], "candidatos": len(cands), "eleitos": sum(1 for c in cands if c["eleito"]),
                "mais_votado": {"sq": mais["sq"], "urna": mais["urna"], "partido": mais["partido"], "votos": mais["votos"]} if mais else None,
            })
        saida.sort(key=lambda g: (-g["votos_total"], g["rotulo"]))
        return saida

    @staticmethod
    def _candidato_prop(c: dict, ele: str, uf: str, posicao: int) -> dict[str, Any]:
        destino = c.get("destino", "")
        return {
            "sq": c["sq"], "numero": c["numero"], "nome": c["nome"], "urna": c["urna"], "partido": c["partido"], "agr": c["agr"],
            "cor": chave_do_partido(c["partido"]), "votos": c["votos"], "pct": c["pct"], "eleito": c["eleito"], "situacao": c["situacao"],
            # só o que foge do normal: voto anulado (ex.: candidatura indeferida) não conta para o partido, e a lista avisa
            "destino": "" if sem_acentos(destino).lower().startswith("valido") else destino,
            "posicao": posicao, "foto": f"/foto/{int(ele)}/{uf}/{c['sq']}",
        }

    def _disputa_proporcional(self, slug: str, turno: int | None) -> Disputa | None:
        cargo = CARGO_POR_SLUG.get(slug)
        if cargo is None or cargo.tipo != "proporcional" or slug not in SLUGS_PROPORCIONAIS:
            return None
        return self.disputa(slug, turno)

    def painel_proporcional(self, slug: str, uf: str, turno: int | None = None) -> dict[str, Any] | None:
        """Deputado numa UF: andamento, vagas por partido/federação, mais votados e (quando o TSE já marcou) eleitos."""
        uf = uf.lower()
        d = self._disputa_proporcional(slug, turno)
        if d is None or uf not in d.ufs:
            return None
        snap = self.store.get(chave("u", d.ele, d.cargo.cd, uf))
        saida: dict[str, Any] = {
            "slug": slug, "nome": d.cargo.nome, "uf": uf, "nome_uf": UF_NOMES[uf], "turno": d.turno, "ele": d.ele,
            "turnos": self.turnos_do_cargo(d.cargo.cd), "disponivel": snap is not None,
        }
        if snap is None:
            return saida
        r = snap.dados
        candidatos = r["candidatos"]
        saida["resultado"] = {
            "ele": r["ele"], "turno": r["turno"], "fase": r["fase"], "idg": r["idg"], "gerado_em": r["gerado_em"],
            "totalizado_em": r["totalizado_em"], "estado": r["estado"], "cargo": r["cargo"],
            "secoes": r["secoes"], "eleitorado": r["eleitorado"], "votos": r["votos"],
        }
        agrupamentos = self._agrupamentos(snap)
        saida["agrupamentos"] = agrupamentos
        saida["vagas_distribuidas"] = sum(g["vagas"] for g in agrupamentos)
        saida["total_candidatos"] = len(candidatos)
        saida["destaques"] = [self._candidato_prop(c, d.ele, uf, i + 1) for i, c in enumerate(candidatos[:DESTAQUES_POR_UF]) if c["votos"] > 0]
        saida["eleitos"] = [self._candidato_prop(c, d.ele, uf, i + 1) for i, c in enumerate(candidatos) if c["eleito"]]
        return saida

    def buscar_candidatos_proporcional(self, slug: str, uf: str, termo: str = "", agr: str = "", pagina: int = 1, tamanho: int = 20,
                                       turno: int | None = None) -> dict[str, Any] | None:
        """Candidatos de uma UF em ordem de votos, com busca por nome (sem acentos) ou número e filtro por partido/federação."""
        uf = uf.lower()
        d = self._disputa_proporcional(slug, turno)
        snap = self.store.get(chave("u", d.ele, d.cargo.cd, uf)) if d is not None and uf in d.ufs else None
        if snap is None:
            return None
        busca = sem_acentos(termo.strip())
        numero = busca if busca.isdigit() else ""
        palavras = [] if numero else busca.split()
        itens = []
        for posicao, c in enumerate(snap.dados["candidatos"], start=1):
            if agr and c["agr"] != agr:
                continue
            if numero and not c["numero"].startswith(numero):
                continue
            if palavras:
                texto = sem_acentos(f"{c['nome']} {c['urna']}")
                if not all(p in texto for p in palavras):
                    continue
            itens.append((posicao, c))
        total = len(itens)
        paginas = max(1, -(-total // tamanho))
        pagina = min(max(1, pagina), paginas)
        corte = itens[(pagina - 1) * tamanho: pagina * tamanho]
        return {"total": total, "pagina": pagina, "paginas": paginas, "itens": [self._candidato_prop(c, d.ele, uf, p) for p, c in corte]}

    def tabela_proporcional(self, slug: str, turno: int | None = None) -> dict[str, Any] | None:
        """Visão nacional de um cargo proporcional: vagas por partido/federação somadas das UFs e uma linha por UF.

        `deputado-estadual` inclui o DF, que elege Deputado Distrital (arquivo à parte, mesma ideia).
        """
        if slug not in ("deputado-federal", "deputado-estadual"):
            return None
        d = self._disputa_proporcional(slug, turno)
        disputas = [d] if d else []
        if slug == "deputado-estadual":
            disputas += [x for x in [self._disputa_proporcional("deputado-distrital", turno)] if x]
        if not disputas:
            return None
        linhas, soma = [], {}
        vagas_total = vagas_distribuidas = 0
        for disp in disputas:
            for uf in disp.ufs:
                base = {"codigo": uf, "nome": UF_NOMES[uf], "cargo": disp.cargo.slug}
                snap = self.store.get(chave("u", disp.ele, disp.cargo.cd, uf))
                if snap is None:
                    linhas.append({**base, "disponivel": False})
                    continue
                r = snap.dados
                grupos = self._agrupamentos(snap)
                vagas = (r["cargo"] or {}).get("vagas") or 0
                vagas_total += vagas
                vagas_distribuidas += sum(g["vagas"] for g in grupos)
                com_votos = [g for g in grupos if g["votos_total"] > 0]
                top = [{
                    "sq": g["id"], "numero": "", "urna": g["rotulo"], "partido": g["rotulo"], "votos": g["votos_total"],
                    "pct": {"t": f"{g['pct_validos']:.2f}".replace(".", ","), "n": g["pct_validos"]}, "eleito": False,
                    "cor": g["cor_partido"], "cor_partido": g["cor_partido"], "vagas": g["vagas"],  # entre UFs vale a cor estável
                    "bancada": True,  # a linha é um partido/federação (não um candidato): o mapa e as dicas falam de vagas
                } for g in com_votos[:3]]
                mais = r["candidatos"][0] if r["candidatos"] and r["candidatos"][0]["votos"] > 0 else None
                linhas.append({
                    **base, "disponivel": True, "andamento": r["estado"]["andamento"], "divulga": r["estado"]["divulga"],
                    "final": r["estado"]["totalizacao_final"], "totalizado_em": r["totalizado_em"],
                    "secoes": {k: r["secoes"].get(k) for k in ("ts", "st", "pst")},
                    "vagas": vagas, "vagas_distribuidas": sum(g["vagas"] for g in grupos), "top": top,
                    "margem_pp": round(top[0]["pct"]["n"] - top[1]["pct"]["n"], 2) if len(top) > 1 else None,
                    "mais_votado": {"sq": mais["sq"], "urna": mais["urna"], "partido": mais["partido"], "votos": mais["votos"],
                                    "cor": chave_do_partido(mais["partido"]), "foto": f"/foto/{int(disp.ele)}/{uf}/{mais['sq']}"} if mais else None,
                })
                for g in grupos:
                    acumulado = soma.setdefault(g["chave"], {
                        "chave": g["chave"], "rotulo": g["rotulo"], "nome": g["nome"], "composicao": g["composicao"], "tipo": g["tipo"],
                        "cor": g["cor_partido"], "vagas": 0, "votos": 0, "ufs": 0,
                    })
                    acumulado["vagas"] += g["vagas"]
                    acumulado["votos"] += g["votos_total"]
                    acumulado["ufs"] += 1 if g["vagas"] else 0
        distribuicao = sorted(soma.values(), key=lambda g: (-g["vagas"], -g["votos"], g["rotulo"]))
        linhas.sort(key=lambda x: x["nome"])
        return {
            "slug": slug, "nome": CARGO_POR_SLUG[slug].nome, "turno": disputas[0].turno, "ele": disputas[0].ele,
            "turnos": self.turnos_do_cargo(disputas[0].cargo.cd),
            "vagas_total": vagas_total, "vagas_distribuidas": vagas_distribuidas, "distribuicao": distribuicao, "ufs": linhas,
        }

    # ---- frescor (volátil: vai em cabeçalhos, nunca no corpo dos dados) -------------------------------------
    def frescor(self) -> dict[str, Any]:
        agora = time.time()
        confirmacoes = [s.obtido_em for s in self.store.itens() if s.tipo in ("u", "ab")]
        ultima = max(confirmacoes, default=None)
        defasagem = None if ultima is None else round(max(0.0, agora - ultima), 1)
        breaker = self.poller.client.breaker if self.poller else None
        restante = breaker.restante() if breaker else 0.0
        return {
            "agora": _iso_epoch(agora),
            "ultima_confirmacao": _iso_epoch(ultima),
            "defasagem_s": defasagem,
            "aguardando_primeiro_contato": ultima is None,
            "desatualizado": ultima is None or defasagem > self.cfg.desatualizado_apos_s,
            "disjuntor": {"aberto": restante > 0, "restante_s": round(restante, 1), "motivo": breaker.motivo if breaker and restante > 0 else None},
        }
