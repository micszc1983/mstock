import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell,
  Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type {
  Forecast, NarrativePoint, ThesisOutcome, ThesisQualityByHorizon,
} from "../lib/types";

// ── Paleta kolorów ───────────────────────────────────────────────────────────
// Każdy kolor jest czytelny na białym i ciemnym tle.
const PALETTE = [
  "#4f86f7", // niebieski
  "#22c55e", // zielony
  "#f59e0b", // bursztynowy
  "#ef4444", // czerwony
  "#a855f7", // fioletowy
  "#14b8a6", // morski
  "#f97316", // pomarańczowy
  "#ec4899", // różowy
  "#84cc16", // limonkowy
  "#06b6d4", // cyjan
];
const C = (i: number) => PALETTE[i % PALETTE.length];

// Kolor słupka wyniku tezy na podstawie wartości
const returnColor = (val: number) =>
  val > 0 ? "#22c55e" : val < 0 ? "#ef4444" : "#94a3b8";

// ── Outcomes Chart ───────────────────────────────────────────────────────────
export function OutcomesChart({ rows }: { rows: ThesisOutcome[] }) {
  const data = rows
    .slice(0, 12)
    .map(r => ({ name: r.horizon, ret: r.realized_return_pct }));

  return (
    <div className="chart-box">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,.07)" />
          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} unit="%" />
          <Tooltip
            formatter={(v: number) => [`${v.toFixed(2)}%`, "Zwrot"]}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Bar dataKey="ret" name="Zwrot %" radius={[6, 6, 0, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={returnColor(entry.ret)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Forecast History Chart ───────────────────────────────────────────────────
export function ForecastHistoryChart({ rows }: { rows: Forecast[] }) {
  const data = rows
    .slice(0, 30)
    .reverse()
    .map(r => ({
      time: new Date(r.generated_at).toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit" }),
      "Oczekiwany zwrot": r.expected_return_pct,
      "Pewność": r.confidence,
    }));

  return (
    <div className="chart-box">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,.07)" />
          <XAxis dataKey="time" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="Oczekiwany zwrot"
            stroke={C(0)}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="Pewność"
            stroke={C(1)}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            strokeDasharray="5 3"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Thesis Quality Chart ─────────────────────────────────────────────────────
export function ThesisQualityChart({ rows }: { rows: ThesisQualityByHorizon[] }) {
  const data = rows.map(r => ({
    horizon: r.horizon,
    "Trafność (%)": parseFloat((r.directional_accuracy * 100).toFixed(1)),
    "Śr. zwrot (%)": parseFloat(r.average_realized_return_pct.toFixed(2)),
  }));

  return (
    <div className="chart-box">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,.07)" />
          <XAxis dataKey="horizon" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} unit="%" />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Trafność (%)"   fill={C(0)} radius={[6, 6, 0, 0]} />
          <Bar dataKey="Śr. zwrot (%)" fill={C(2)} radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Narrative History Chart ───────────────────────────────────────────────────
export function NarrativeHistoryChart({ rows }: { rows: NarrativePoint[] }) {
  const keys = Array.from(
    new Set(rows.flatMap(r => Object.keys(r.narrative_scores)))
  ).slice(0, 8);

  const data = rows.map(r => ({
    date: new Date(r.date).toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit" }),
    ...r.narrative_scores,
  }));

  const labelPL: Record<string, string> = {
    ai_growth:          "Wzrost AI",
    margin_pressure:    "Presja marż",
    demand_strength:    "Popyt silny",
    demand_slowdown:    "Popyt słabnie",
    regulation_risk:    "Ryzyko regulacji",
    valuation_stretch:  "Przewartościowanie",
    safe_haven:         "Bezpieczna przystań",
    rates_pressure:     "Presja stóp",
    dollar_pressure:    "Presja dolara",
    central_bank_buying:"Zakupy CB",
    industrial_demand:  "Popyt przemysłowy",
    supply_disruption:  "Zakłócenia podaży",
  };
  const label = (k: string) => labelPL[k] ?? k.replace(/_/g, " ");

  return (
    <div className="chart-box">
      <ResponsiveContainer width="100%" height={340}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,.07)" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} domain={[0, 1]} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
          <Tooltip
            formatter={(v: number, name: string) => [`${(v * 100).toFixed(1)}%`, label(name)]}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Legend
            wrapperStyle={{ fontSize: 11 }}
            formatter={(value) => label(value)}
          />
          {keys.map((k, i) => (
            <Line
              key={k}
              type="monotone"
              dataKey={k}
              name={k}
              stroke={C(i)}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Price History Chart ───────────────────────────────────────────────────────
type PriceRange = "5D" | "1M" | "3M" | "1R" | "Max";

const RANGES: { label: string; key: PriceRange; days: number | null }[] = [
  { label: "5D",  key: "5D",  days: 5   },
  { label: "1M",  key: "1M",  days: 30  },
  { label: "3M",  key: "3M",  days: 90  },
  { label: "1R",  key: "1R",  days: 365 },
  { label: "Max", key: "Max", days: null },
];

export function PriceHistoryChart({ bars, symbol, currency = "USD" }: { bars: { timestamp: string; close: number; volume: number }[]; symbol: string; currency?: string }) {
  const [range, setRange] = useState<PriceRange>("1M");

  if (!bars || bars.length === 0) {
    return (
      <div className="chart-box" style={{ paddingBottom: "8px", display: "flex", alignItems: "center", justifyContent: "center", minHeight: 120 }}>
        <div style={{ textAlign: "center", color: "var(--text-3)" }}>
          <div style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "0.25rem" }}>{symbol} — brak danych cenowych</div>
          <div style={{ fontSize: "0.78rem" }}>Kliknij <strong>Sync</strong> aby pobrać dane od providera</div>
        </div>
      </div>
    );
  }

  // Deduplikuj po dacie — zachowaj tylko jeden wpis na dzień
  const byDate = new Map<string, typeof bars[0]>();
  for (const b of bars) {
    const d = b.timestamp.slice(0, 10);
    if (!byDate.has(d) || b.timestamp > byDate.get(d)!.timestamp) byDate.set(d, b);
  }
  const allSorted = [...byDate.values()].sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  // Filtruj według wybranego zakresu
  const selectedDays = RANGES.find(r => r.key === range)?.days ?? null;
  const filtered = selectedDays === null
    ? allSorted
    : allSorted.slice(-selectedDays);

  // Format daty zależnie od rozpiętości
  const dateFormatter = (ts: string) => {
    const d = new Date(ts);
    if (selectedDays !== null && selectedDays <= 30)
      return d.toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit" });
    if (selectedDays !== null && selectedDays <= 365)
      return d.toLocaleDateString("pl-PL", { month: "2-digit", year: "2-digit" });
    return d.toLocaleDateString("pl-PL", { month: "2-digit", year: "numeric" });
  };

  const data = filtered.map(b => ({
    date: dateFormatter(b.timestamp),
    Cena: b.close,
  }));

  const prices = data.map(d => d.Cena);
  const minP = Math.min(...prices) * 0.995;
  const maxP = Math.max(...prices) * 1.005;
  const first = prices[0] ?? 0;
  const last  = prices[prices.length - 1] ?? 0;
  const change = first > 0 ? ((last - first) / first) * 100 : 0;
  const lineColor = change >= 0 ? "#22c55e" : "#ef4444";

  return (
    <div className="chart-box" style={{ paddingBottom: "8px" }}>
      {/* Header: symbol + cena + zmiana + przyciski zakresu */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "8px", paddingLeft: "4px", flexWrap: "wrap" }}>
        <span style={{ fontWeight: 700, fontSize: "1.1rem" }}>{symbol}</span>
        <span style={{ fontSize: "1.35rem", fontWeight: 700 }}>
          {last.toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {currency}
        </span>
        <span style={{ fontSize: "0.85rem", fontWeight: 600, color: change >= 0 ? "#22c55e" : "#ef4444" }}>
          {change >= 0 ? "+" : ""}{change.toFixed(2)}% ({filtered.length}d)
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: "2px" }}>
          {RANGES.map(r => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              style={{
                padding: "2px 8px",
                fontSize: "0.72rem",
                fontWeight: range === r.key ? 700 : 400,
                border: "1px solid var(--border)",
                borderRadius: r.key === "5D" ? "5px 0 0 5px" : r.key === "Max" ? "0 5px 5px 0" : "0",
                borderLeft: r.key !== "5D" ? "none" : undefined,
                background: range === r.key ? "var(--accent)" : "var(--bg-subtle)",
                color: range === r.key ? "#fff" : "var(--text-2)",
                cursor: "pointer",
              }}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,.06)" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10 }}
            interval={Math.max(1, Math.floor(data.length / 8))}
          />
          <YAxis
            domain={[minP, maxP]}
            tick={{ fontSize: 10 }}
            width={60}
            tickFormatter={v => v.toLocaleString("pl-PL", { maximumFractionDigits: 0 })}
          />
          <Tooltip
            formatter={(v: number) => [v.toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " " + currency, "Kurs zamknięcia"]}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Line
            type="monotone"
            dataKey="Cena"
            stroke={lineColor}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
