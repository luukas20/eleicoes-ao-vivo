// Consulta periódica à API do painel. O navegador revalida o ETag sozinho; aqui só evitamos
// redesenhar quando o ETag não mudou, e repassamos o "frescor" (idade da última confirmação do TSE),
// que viaja em cabeçalhos e chega mesmo nas respostas 304.

// `?intervalo=<ms>` permite acelerar/desacelerar a consulta (testes e telões); fica entre 2 s e 2 min.
function intervaloDaUrl(padrao) {
  const pedido = Number(new URLSearchParams(window.location.search).get("intervalo"));
  return Number.isFinite(pedido) && pedido > 0 ? Math.min(120000, Math.max(2000, pedido)) : padrao;
}

export class Atualizador {
  /**
   * aoDados(dados): dado novo (ETag mudou). aoSemMudanca(): resposta igual à anterior.
   * aoIndisponivel(mensagem, status): 404/503 da API (ex.: dados ainda não carregados).
   */
  constructor({ url, intervaloMs = 10000, aoDados, aoFrescor, aoErro, aoIndisponivel, aoSemMudanca }) {
    intervaloMs = intervaloDaUrl(intervaloMs);
    Object.assign(this, { url, intervaloMs, aoDados, aoFrescor, aoErro, aoIndisponivel, aoSemMudanca });
    this.etag = null;
    this.carregando = false;
    this.rapido = null;
  }

  iniciar() {
    this.buscar();
    setInterval(() => {
      if (!document.hidden) this.buscar();
    }, this.intervaloMs);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) this.buscar();
    });
  }

  /** Agenda uma consulta extra daqui a `ms` (ex.: enquanto se espera o primeiro arquivo de um município). */
  buscarEm(ms) {
    clearTimeout(this.rapido);
    this.rapido = setTimeout(() => this.buscar(), ms);
  }

  async buscar() {
    if (this.carregando) return;
    this.carregando = true;
    try {
      const resp = await fetch(this.url, { headers: { Accept: "application/json" } });
      const defasagem = parseFloat(resp.headers.get("X-Defasagem-S"));
      this.aoFrescor?.({
        defasagemS: Number.isNaN(defasagem) ? null : defasagem,
        desatualizado: resp.headers.get("X-Desatualizado") === "1",
        disjuntor: resp.headers.get("X-Disjuntor") === "1",
        recebidoEm: performance.now(),
      });
      if (resp.status === 404 || resp.status === 503) {
        const corpo = await resp.json().catch(() => ({}));
        this.aoIndisponivel?.(corpo.erro || "Dados ainda indisponíveis", resp.status);
        return;
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const etag = resp.headers.get("ETag");
      if (etag && etag === this.etag) {
        this.aoSemMudanca?.(); // nada novo do TSE desde a última vez
        return;
      }
      this.etag = etag;
      this.aoDados(await resp.json());
    } catch (erro) {
      this.aoErro?.(erro);
    } finally {
      this.carregando = false;
    }
  }
}
