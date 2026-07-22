import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import type { Asset, SimulatorPerformance, ThesisQualitySummary, IntradayBacktest } from "../lib/types";

interface Props {
  assets: Asset[];
  selectedAssetId: string;
}

function fmtPrice(value: number, currency: string): string {
  if (currency === "PLN") return `${value.toFixed(2)} zł`;
  return `$${value.toFixed(2)}`;
}

function fmtPct(value: number): string {
  return (value >= 0 ? "+" : "") + value.toFixed(2) + "%";
}

function fmtAmount(value: number, currency: string): string {
  const formatted = value.toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency === "PLN" ? `${formatted} zł` : `$${formatted}`;
}

function ReturnCard({ label, period, currency }: {
  label: string;
  period: SimulatorPerformance["returns"][number];
  currency: string;
}) {
  const color = period.available && period.return_pct != null
    ? (period.return_pct >= 0 ? "#22c55e" : "#ef4444")
    : "#64748b";

  return (
    <div style={{
      background: "var(--surface-2, #1e293b)",
      border: "1px solid var(--border, #334155)",
      borderRadius: 8,
      padding: "16px 20px",
      flex: 1,
      minWidth: 0,
    }}>
      <div style={{ fontSize: 11, color: "var(--text-3, #64748b)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </div>
      {period.available && period.return_pct != null ? (
        <>
          <div style={{ fontSize: 24, fontWeight: 700, color, lineHeight: 1.1 }}>
            {fmtPct(period.return_pct)}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-3, #64748b)", marginTop: 6 }}>
            {fmtPrice(period.start_price!, currency)} → {fmtPrice(period.end_price, currency)}
          </div>
        </>
      ) : (
        <div style={{ fontSize: 16, color: "#475569" }}>— brak danych</div>
      )}
    </div>
  );
}

function StatRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "5px 0", borderBottom: "1px solid var(--border, #1e293b)" }}>
      <span style={{ fontSize: 13, color: "var(--text-3, #64748b)" }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: color ?? "var(--text-1, #e2e8f0)" }}>{value}</span>
    </div>
  );
}

export function SimulatorTab({ assets, selectedAssetId }: Props) {
  const stocks = assets.filter((a) => a.type === "stock");
  const selectedId = stocks.some((s) => s.id === selectedAssetId) ? selectedAssetId : (stocks[0]?.id ?? "");
  const asset = assets.find((a) => a.id === selectedId);

  const [perf, setPerf] = useState<SimulatorPerformance | null>(null);
  const [thesis, setThesis] = useState<ThesisQualitySummary | null>(null);
  const [backtest, setBacktest] = useState<IntradayBacktest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [simAmount, setSimAmount] = useState<string>("10000");
  const [simPeriod, setSimPeriod] = useState<"1w" | "1m" | "3m" | "1y">("1m");

  const load = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const [p, t, b] = await Promise.allSettled([
        api.simulatorPerformance(id),
        api.thesisQualitySummary(id),
        api.intradayBacktest(id),
      ]);
      setPerf(p.status === "fulfilled" ? p.value : null);
      setThesis(t.status === "fulfilled" ? t.value : null);
      setBacktest(b.status === "fulfilled" ? b.value : null);
    } catch {
      setError("Błąd pobierania danych symulatora.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) load(selectedId);
  }, [selectedId, load]);

  const currency = asset?.currency ?? "PLN";
  const simAmountNum = parseFloat(simAmount.replace(",", ".")) || 0;

  const selectedPeriod = perf?.returns.find((r) => r.key === simPeriod);
  let simResult: number | null = null;
  let simGain: number | null = null;
  if (selectedPeriod?.available && selectedPeriod.return_pct != null && simAmountNum > 0) {
    simGain = simAmountNum * (selectedPeriod.return_pct / 100);
    simResult = simAmountNum + simGain;
  }

  const backtestWinRate = backtest?.win_rate != null ? (backtest.win_rate * 100) : null;
  const thesisAccuracy = thesis?.directional_accuracy != null ? (thesis.directional_accuracy * 100) : null;

  return (
    <div style={{ padding: "16px 0", maxWidth: 900 }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "var(--text-1, #e2e8f0)" }}>
          Symulator inwestycji
        </h2>
        {asset && (
          <div style={{ fontSize: 12, color: "var(--text-3, #64748b)", marginTop: 3 }}>
            {asset.symbol} — {asset.name}
          </div>
        )}
      </div>

      {loading && (
        <div style={{ color: "var(--text-3, #64748b)", fontSize: 13, padding: "20px 0" }}>Ładowanie danych…</div>
      )}
      {error && (
        <div style={{ color: "#ef4444", fontSize: 13, padding: "8px 12px", background: "#1e1a1a", borderRadius: 6 }}>{error}</div>
      )}

      {!loading && perf && (
        <>
          {/* ── Zwroty cenowe ── */}
          <section style={{ marginBottom: 28 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-3, #64748b)", marginBottom: 10 }}>
              Zwroty cenowe
            </div>
            {perf.has_enough_data ? (
              <div style={{ display: "flex", gap: 10 }}>
                {perf.returns.map((r) => (
                  <ReturnCard key={r.key} label={r.label} period={r} currency={currency} />
                ))}
              </div>
            ) : (
              <div style={{ color: "#64748b", fontSize: 13 }}>Brak wystarczającej historii cen dla tego aktywa.</div>
            )}
            {perf.last_price_date && (
              <div style={{ fontSize: 11, color: "#475569", marginTop: 8 }}>
                Ostatnia cena: {fmtPrice(perf.current_price!, currency)} ({new Date(perf.last_price_date).toLocaleDateString("pl-PL")})
              </div>
            )}
          </section>

          {/* ── Wirtualna inwestycja ── */}
          {perf.has_enough_data && (
            <section style={{ marginBottom: 28 }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-3, #64748b)", marginBottom: 10 }}>
                Wirtualna inwestycja
              </div>
              <div style={{
                background: "var(--surface-2, #1e293b)",
                border: "1px solid var(--border, #334155)",
                borderRadius: 8,
                padding: "16px 20px",
              }}>
                <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap", marginBottom: 16 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-2, #94a3b8)" }}>
                    Kwota ({currency === "PLN" ? "zł" : "$"}):
                    <input
                      type="number"
                      value={simAmount}
                      onChange={(e) => setSimAmount(e.target.value)}
                      min={0}
                      step={1000}
                      style={{
                        width: 110,
                        padding: "4px 8px",
                        background: "var(--surface-1, #0f172a)",
                        border: "1px solid var(--border, #334155)",
                        borderRadius: 4,
                        color: "var(--text-1, #e2e8f0)",
                        fontSize: 13,
                      }}
                    />
                  </label>
                  <div style={{ display: "flex", gap: 6 }}>
                    {(["1w", "1m", "3m", "1y"] as const).map((key) => {
                      const p = perf.returns.find((r) => r.key === key);
                      const label = key === "1w" ? "1 tydzień" : key === "1m" ? "1 miesiąc" : key === "3m" ? "3 mies." : "1 rok";
                      return (
                        <button
                          key={key}
                          onClick={() => setSimPeriod(key)}
                          disabled={!p?.available}
                          style={{
                            padding: "4px 12px",
                            borderRadius: 4,
                            border: simPeriod === key ? "1px solid var(--accent, #6366f1)" : "1px solid var(--border, #334155)",
                            background: simPeriod === key ? "var(--accent, #6366f1)" : "transparent",
                            color: !p?.available ? "#475569" : simPeriod === key ? "#fff" : "var(--text-2, #94a3b8)",
                            fontSize: 12,
                            cursor: p?.available ? "pointer" : "not-allowed",
                          }}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {simResult != null && simGain != null ? (
                  <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 13, color: "var(--text-3, #64748b)" }}>
                      {fmtAmount(simAmountNum, currency)}
                    </span>
                    <span style={{ fontSize: 18, color: "var(--text-3, #64748b)" }}>→</span>
                    <span style={{ fontSize: 24, fontWeight: 700, color: simGain >= 0 ? "#22c55e" : "#ef4444" }}>
                      {fmtAmount(simResult, currency)}
                    </span>
                    <span style={{ fontSize: 14, fontWeight: 600, color: simGain >= 0 ? "#22c55e" : "#ef4444" }}>
                      ({simGain >= 0 ? "+" : ""}{fmtAmount(simGain, currency)}, {selectedPeriod?.return_pct != null ? fmtPct(selectedPeriod.return_pct) : ""})
                    </span>
                  </div>
                ) : (
                  <div style={{ color: "#475569", fontSize: 13 }}>Brak danych dla wybranego okresu.</div>
                )}
              </div>
            </section>
          )}
        </>
      )}

      {/* ── Skuteczność historycznych rekomendacji ── */}
      {!loading && (thesis || backtest) && (
        <section>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-3, #64748b)", marginBottom: 10 }}>
            Historyczna skuteczność rekomendacji
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>

            {/* Backtest intraday */}
            {backtest && (
              <div style={{
                background: "var(--surface-2, #1e293b)",
                border: "1px solid var(--border, #334155)",
                borderRadius: 8,
                padding: "14px 18px",
                flex: 1,
                minWidth: 220,
              }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-2, #94a3b8)", marginBottom: 10 }}>
                  Sygnały intraday ({backtest.resolution} min)
                </div>
                <StatRow label="Łączna liczba sygnałów" value={String(backtest.total_signals)} />
                <StatRow
                  label="Trafność"
                  value={backtestWinRate != null ? `${backtestWinRate.toFixed(1)}%` : "—"}
                  color={backtestWinRate != null ? (backtestWinRate >= 55 ? "#22c55e" : backtestWinRate >= 45 ? "#f59e0b" : "#ef4444") : undefined}
                />
                <StatRow
                  label="Expectancy"
                  value={backtest.expectancy != null ? fmtPct(backtest.expectancy) : "—"}
                  color={backtest.expectancy != null ? (backtest.expectancy > 0 ? "#22c55e" : "#ef4444") : undefined}
                />
                {backtest.avg_win_pct != null && (
                  <StatRow label="Śr. zysk na transakcji" value={fmtPct(backtest.avg_win_pct)} color="#22c55e" />
                )}
                {backtest.avg_loss_pct != null && (
                  <StatRow label="Śr. strata na transakcji" value={fmtPct(backtest.avg_loss_pct)} color="#ef4444" />
                )}
                {backtest.total_return_pct != null && (
                  <StatRow
                    label="Łączny zwrot"
                    value={fmtPct(backtest.total_return_pct)}
                    color={backtest.total_return_pct >= 0 ? "#22c55e" : "#ef4444"}
                  />
                )}
                <div style={{ fontSize: 11, color: "#475569", marginTop: 8 }}>
                  Backtest: {backtest.lookback_days} dni, {backtest.candles_count} świec
                </div>
              </div>
            )}

            {/* Trafność tez */}
            {thesis && (
              <div style={{
                background: "var(--surface-2, #1e293b)",
                border: "1px solid var(--border, #334155)",
                borderRadius: 8,
                padding: "14px 18px",
                flex: 1,
                minWidth: 220,
              }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-2, #94a3b8)", marginBottom: 10 }}>
                  Tezy analityczne
                </div>
                <StatRow label="Przeanalizowanych" value={String(thesis.total_outcomes)} />
                <StatRow
                  label="Trafność kierunkowa"
                  value={thesisAccuracy != null ? `${thesisAccuracy.toFixed(1)}%` : "—"}
                  color={thesisAccuracy != null ? (thesisAccuracy >= 60 ? "#22c55e" : thesisAccuracy >= 45 ? "#f59e0b" : "#ef4444") : undefined}
                />
                <StatRow
                  label="Śr. zrealizowany zwrot"
                  value={fmtPct(thesis.average_realized_return_pct)}
                  color={thesis.average_realized_return_pct >= 0 ? "#22c55e" : "#ef4444"}
                />
                {thesis.bullish_win_rate > 0 && (
                  <StatRow label="Trafność bycza" value={`${(thesis.bullish_win_rate * 100).toFixed(1)}%`} color="#22c55e" />
                )}
                {thesis.bearish_win_rate > 0 && (
                  <StatRow label="Trafność niedźwiedzia" value={`${(thesis.bearish_win_rate * 100).toFixed(1)}%`} color="#ef4444" />
                )}
                {thesis.total_outcomes === 0 && (
                  <div style={{ fontSize: 12, color: "#475569", marginTop: 8 }}>Brak ocenionych tez dla tego aktywa.</div>
                )}
              </div>
            )}

          </div>
        </section>
      )}

      {!loading && !perf && !thesis && !backtest && !error && (
        <div style={{ color: "#475569", fontSize: 13 }}>Brak danych dla wybranego aktywa.</div>
      )}
    </div>
  );
}