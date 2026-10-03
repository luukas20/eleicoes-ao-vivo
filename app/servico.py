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
from .cores import Cores
from .store import Snapshot, Store, chave
from .tse.dominio import BRASIL, CARGO_POR_SLUG, UF_NOMES, UFS, nome_abrangencia
from .tse.parse import BRT, sem_acentos
from .tse.urls import TseUrls

CARGOS_DA_PAGINA_UF = ("presidente", "governador", "senador")
TTL_MUNICIPIO_S = 90.0  # um município é consultado ao TSE enquanto alguém o pedir a cada < 90 s


class NaoEncontrado(Exception):
    """UF ou município que não existe nos arquivos do TSE."""


class Indisponivel(Exception):
    """Ainda não dá para atender (lista de municípios não carregada ou limite de acompanhamentos atingido)."""


def _iso_epoch(epoch: float | None) -> str | None:
    return datetime.fromtimestamp(epoch, BRT).isoformat(timespec="seconds") if epoch else None


class Servico:
    def __init__(self, settings: Settings, store: Store, *, poller=None, cores: Cores | None = None):
        self.cfg = settings
        self.store = store
        self.poller = poller
        self.cores = cores or Cores()
        self._cache_disputas: tuple[str, list[Disputa]] = ("", [])
        self._cache_municipios: tuple[tuple, dict] = ((), {})
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
        if (cargo["cd"] == 1 and abr["tipo"] == "br") or (cargo["cd"] in (3, 5) and abr["tipo"] == "uf"):
            self.cores.observar(
                self.escopo_cores(r["ele"], cargo["cd"], abr["codigo"]), r["candidatos"],
                pct_secoes=r["secoes"].get("pst", {}).get("n", 0.0),
            )

    @staticmethod
    def escopo_cores(ele: str | int, cargo: int, uf: str) -> str:
        """Presidente: mesma cor em todo lugar da eleição. Demais cargos: por UF."""
        return f"{ele}:1" if cargo == 1 else f"{ele}:{cargo}:{uf}"

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
        turno = turno or self.turno_padrao()
        return next((d for d in self.disputas() if d.cargo.cd == cargo.cd and d.turno == turno), None)

    # ---- peças ---------------------------------------------------------------------------------------
    def _candidato(self, c: dict, ele: str, escopo_foto: str, escopo_cores: str) -> dict:
        return {**c, "cor": self.cores.slot(escopo_cores, c["sq"]), "foto": f"/foto/{int(ele)}/{escopo_foto}/{c['sq']}"}

    def _resumo(self, c: dict | None, escopo_cores: str) -> dict | None:
        if c is None:
            return None
        return {k: c[k] for k in ("sq", "numero", "urna", "partido", "votos", "pct", "eleito")} | {"cor": self.cores.slot(escopo_cores, c["sq"])}

    def _resultado(self, snap: Snapshot, d: Disputa, uf: str, nome_local: str | None = None) -> dict[str, Any]:
        r = snap.dados
        escopo_foto = BRASIL if d.cargo.cd == 1 else uf
        escopo_cores = self.escopo_cores(d.ele, d.cargo.cd, uf)
        return {
            "ele": r["ele"], "turno": r["turno"], "fase": r["fase"], "idg": r["idg"],
            "gerado_em": r["gerado_em"], "totalizado_em": r["totalizado_em"],
            "abrangencia": {**r["abrangencia"], "nome": nome_local or nome_abrangencia(r["abrangencia"]["codigo"])},
            "cargo": r["cargo"], "estado": r["estado"],
            "secoes": r["secoes"], "eleitorado": r["eleitorado"], "votos": r["votos"],
            "candidatos": [self._candidato(c, d.ele, escopo_foto, escopo_cores) for c in r["candidatos"]],
        }

    def _linha_uf(self, d: Disputa, uf: str) -> dict[str, Any]:
        snap = self.store.get(chave("u", d.ele, d.cargo.cd, uf))
        base = {"codigo": uf, "nome": nome_abrangencia(uf)}
        if snap is None:
            return {**base, "disponivel": False}
        r = snap.dados
        escopo_cores = self.escopo_cores(d.ele, d.cargo.cd, uf)
        vagas = (r["cargo"] or {}).get("vagas") or 1
        com_votos = [c for c in r["candidatos"] if c["votos"] > 0]
        top = [self._resumo(c, escopo_cores) for c in com_votos[: max(2, vagas + 1)]]
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
        escopo = self.escopo_cores(d.ele, d.cargo.cd, BRASIL)
        itens = [
            {"sq": c["sq"], "cor": self.cores.slot(escopo, c["sq"]), "urna": c["urna"], "numero": c["numero"], "partido": c["partido"]}
            for c in snap.dados["candidatos"]
        ]
        return sorted((i for i in itens if i["cor"] > 0), key=lambda i: i["cor"])

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
            "slug": slug, "nome": d.cargo.nome, "turno": d.turno, "ele": d.ele, "turnos": self.turnos(),
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
        return {"uf": uf, "nome": UF_NOMES[uf], "turno": turno, "turnos": self.turnos(), "disputas": disputas_uf}

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
