export function formatPct(value: number, digits = 2) { return `${value.toFixed(digits)}%`; }
export function formatRatio(value: number, digits = 1) { return `${(value * 100).toFixed(digits)}%`; }
export function titleize(value: string | null | undefined) { return value ? value.replaceAll("_", " ") : "—"; }
