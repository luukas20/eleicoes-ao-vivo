// Formatação em pt-BR. Os percentuais do TSE são exibidos como publicados (ex.: "45,32"); aqui só
// formatamos contadores, horários e os derivados calculados pelo painel.

const FUSO = "America/Sao_Paulo";

export function inteiro(n) {
  return Number(n).toLocaleString("pt-BR");
}

// 158745502 -> "158,7 mi"
export function compacto(n) {
  const v = Number(n);
  if (v >= 1e9) return (v / 1e9).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " bi";
  if (v >= 1e6) return (v / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " mi";
  if (v >= 1e4) return (v / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " mil";
  return inteiro(v);
}

export function pct(p) {
  return p && p.t !== undefined && p.t !== "" ? `${p.t}%` : "—";
}

export function hora(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: FUSO });
}

export function dataLonga(isoData) {
  if (!isoData) return "";
  return new Date(`${isoData}T12:00:00-03:00`).toLocaleDateString("pt-BR", {
    weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: FUSO,
  });
}

export function idade(segundos) {
  const s = Math.max(0, Math.round(segundos));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  return `${Math.floor(s / 3600)} h`;
}

// diferença em pontos percentuais entre o 1º e o 2º colocados (cálculo do painel)
export function pontos(pp) {
  if (pp === null || pp === undefined) return "—";
  return `${pp.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} p.p.`;
}

export function turnoPorExtenso(turno) {
  return turno === 2 ? "Segundo turno" : "Primeiro turno";
}
