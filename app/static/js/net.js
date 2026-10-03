// Consulta periódica à API do painel. O navegador revalida o ETag sozinho; aqui só evitamos
// redesenhar quando o ETag não mudou, e repassamos o "frescor" (idade da última confirmação do TSE),
// que viaja em cabeçalhos e chega mesmo nas respostas 304.

// `?intervalo=<ms>` permite acelerar/desacelerar a consulta (testes e telões); fica entre 2 s e 2 min.
function intervaloDaUrl(padrao) {
  const pedido = Number(new URLSearchParams(window.location.search).get("intervalo"));
  return Number.isFinite(pedido) && pedido > 0 ? Math.min(120000, Math.max(2000, pedido)) : padrao;
}

export class Atualizador {
  constructor({ url, intervaloMs = 10000, aoDados, aoFrescor, aoErro, aoIndisponivel }) {
    intervaloMs = intervaloDaUrl(intervaloMs);
    Object.assign(this, { url, intervaloMs, aoDados, aoFrescor, aoErro, aoIndisponivel });
    this.etag = null;
    this.carregando = false;
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
      if (resp.status === 404) {
        const corpo = await resp.json().catch(() => ({}));
        this.aoIndisponivel?.(corpo.erro || "Dados ainda indisponíveis");
        return;
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const etag = resp.headers.get("ETag");
      if (etag && etag === this.etag) return; // nada novo do TSE desde a última vez
      this.etag = etag;
      this.aoDados(await resp.json());
    } catch (erro) {
      this.aoErro?.(erro);
    } finally {
      this.carregando = false;
    }
  }
}
