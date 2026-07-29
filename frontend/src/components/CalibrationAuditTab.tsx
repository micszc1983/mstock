import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { RecommendationAudit, RecommendationJournalRecord, RecommendationStrategyMetrics } from "../lib/types";

const labels: Record<string, string> = {
  calibrated: "Nowa kalibracja",
  legacy_feature_rule: "Stara reguła 62/38",
  buy_hold: "Kup i trzymaj",
  always_flat: "Zawsze bez pozycji",
};

const pct = (value: number | null | undefined, digits = 2) => value == null ? "—" : `${value.toFixed(digits)}%`;
const num = (value: number | null | undefined, digits = 2) => value == null ? "—" : value.toFixed(digits);
const changeLabels: Record<RecommendationJournalRecord["change_type"], string> = {
  initial: "pierwszy zapis",
  legacy: "wpis historyczny",
  action: "zmiana decyzji",
  position: "zmiana pozycji",
  data_quality: "zmiana danych",
  calibration: "zmiana kalibracji",
  signals: "zmiana sygnałów",
};

function MetricTable({ strategies }: { strategies: Record<string, RecommendationStrategyMetrics> }) {
  return <div style={{ overflowX: "auto" }}><table style={{ width: "100%" }}><thead><tr>
    <th>Strategia</th><th>Transakcje</th><th>Pokrycie</th><th>Win rate</th><th>Śr. netto</th>
    <th>Profit factor</th><th>Wynik portfela*</th><th>Max DD</th><th>Sharpe</th><th>Sortino</th>
  </tr></thead><tbody>{Object.entries(strategies).map(([key, m]) => <tr key={key}>
    <td><strong>{labels[key] ?? key}</strong></td><td>{m.trades}</td><td>{pct(m.coverage_pct, 1)}</td>
    <td>{pct(m.win_rate_pct, 1)}</td><td>{pct(m.avg_net_return_pct)}</td><td>{num(m.profit_factor)}</td>
    <td>{pct(m.portfolio_return_pct)}</td><td>{pct(m.max_drawdown_pct)}</td><td>{num(m.sharpe)}</td><td>{num(m.sortino)}</td>
  </tr>)}</tbody></table></div>;
}

export function CalibrationAuditTab() {
  const [audit, setAudit] = useState<RecommendationAudit | null>(null);
  const [journal, setJournal] = useState<RecommendationJournalRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    const [latest, rows] = await Promise.all([
      api.latestRecommendationAudit().catch(() => null),
      api.recommendationJournal(100).catch(() => []),
    ]);
    setAudit(latest); setJournal(rows);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function runAudit() {
    setBusy(true); setMessage("Audyt trenuje kolejne foldy wyłącznie na danych historycznych…");
    try {
      setAudit(await api.runRecommendationAudit(3));
      setMessage("Audyt zakończony i zapisany.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally { setBusy(false); }
  }

  async function snapshot() {
    setBusy(true); setMessage("");
    try {
      const result = await api.snapshotRecommendationJournal();
      setMessage(`Dziennik: ${result.inserted} nowych snapshotów, ${result.evaluated} wyników uzupełnionych.`);
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }

  const card: React.CSSProperties = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, padding: 14 };
  return <div style={{ padding: "16px 0" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
      <div><h2 style={{ margin: 0 }}>Audyt kalibracji</h2><p style={{ color: "var(--text-3)", fontSize: 13 }}>
        Walk-forward z 20 sesjami embargo, kosztami i nietkniętymi blokami testowymi.
      </p></div>
      <div style={{ display: "flex", gap: 8 }}><button disabled={busy} onClick={runAudit}>{busy ? "Pracuję…" : "Uruchom audyt"}</button>
        <button disabled={busy} onClick={snapshot}>Zapisz snapshot dziennika</button></div>
    </div>
    {message && <p style={{ color: "var(--text-2)" }}>{message}</p>}

    {!audit ? <div style={card}>Brak zapisanego audytu. Uruchom go pierwszy raz.</div> : <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 10 }}>
        {[["Ocenione rekordy", audit.evaluated_rows], ["Foldy", audit.fold_count], ["Embargo", `${audit.embargo_sessions} sesji`],
          ["Wykluczone anomalie", audit.excluded_outliers], ["Brier", audit.calibration.multiclass_brier.toFixed(4)],
          ["ECE", audit.calibration.ece.toFixed(4)], ["Trafność transakcji", pct(audit.calibration.trade_direction_accuracy_pct, 1)]].map(([label, value]) =>
          <div key={String(label)} style={card}><small style={{ color: "var(--text-3)" }}>{label}</small><div style={{ fontSize: 20, fontWeight: 700, marginTop: 4 }}>{value}</div></div>)}
      </div>
      <h3>Porównanie strategii</h3><MetricTable strategies={audit.strategies} />
      <p style={{ color: "var(--text-3)", fontSize: 11 }}>* Zagregowany wynik równoważonego koszyka sygnałów 5-sesyjnych; okna częściowo się nakładają.</p>

      <h3>Rynek i reżim</h3>
      <div style={{ overflowX: "auto" }}><table><thead><tr><th>Segment</th><th>Sygnały</th><th>Transakcje</th><th>Pokrycie</th><th>Win rate</th><th>Śr. netto</th><th>Max DD</th></tr></thead><tbody>
        {[...audit.by_market.map(x => ({ ...x, name: `Rynek: ${x.name}` })), ...audit.by_regime.map(x => ({ ...x, name: `Reżim: ${x.name}` }))].map(row =>
          <tr key={row.name}><td>{row.name}</td><td>{row.signals}</td><td>{row.trades}</td><td>{pct(row.coverage_pct, 1)}</td><td>{pct(row.win_rate_pct, 1)}</td><td>{pct(row.avg_net_return_pct)}</td><td>{pct(row.max_drawdown_pct)}</td></tr>)}
      </tbody></table></div>
      <details style={{ marginTop: 12 }}><summary>Foldy i kontrola przecieku</summary><ul>{audit.folds.map(f => <li key={f.fold}>
        Fold {f.fold}: trening przed {f.train_end_exclusive}, embargo {f.embargo_sessions} sesji, test {f.test_start}–{f.test_end} (n={f.test_rows}).
      </li>)}</ul></details>
    </>}

    <h3 style={{ marginTop: 24 }}>Dziennik rekomendacji</h3>
    <p style={{ color: "var(--text-3)", fontSize: 12 }}>
      Każda materialna zmiana w obrębie tej samej świecy tworzy kolejną rewizję. Identyczny wynik nie jest zapisywany ponownie.
    </p>
    <div style={{ overflowX: "auto" }}><table><thead><tr><th>Zapisano</th><th>Świeca</th><th>Aktywo</th><th>Rewizja</th><th>Decyzja</th><th>Co się zmieniło</th><th>Rynek/reżim</th><th>Pewność</th><th>Przewaga netto</th><th>1d</th><th>5d</th><th>20d</th><th>Flaga jakości</th></tr></thead><tbody>
      {journal.map(row => <tr key={row.id}>
        <td style={{ whiteSpace: "nowrap" }}>{new Date(row.created_at).toLocaleString("pl-PL")}</td>
        <td style={{ whiteSpace: "nowrap" }}>{new Date(row.snapshot_at).toLocaleString("pl-PL")}</td>
        <td>{row.asset_id.toUpperCase()}</td>
        <td><strong>r{row.revision}</strong><br/><small style={{ color: "var(--text-3)", whiteSpace: "nowrap" }}>{changeLabels[row.change_type] ?? row.change_type}</small></td>
        <td>{row.displayed_action}{row.meta_gate_applied ? " ⛔ meta" : ""}</td>
        <td style={{ minWidth: 260 }}>
          <span title={row.rationale ?? row.no_trade_reason ?? undefined}>{row.change_summary ?? "—"}</span>
          {row.no_trade_reason && <div style={{ marginTop: 3, color: "var(--text-3)", fontSize: 11 }}>{row.no_trade_reason}</div>}
        </td>
        <td>{row.market}/{row.regime}</td><td>{pct(row.confidence, 1)}</td><td>{pct(row.expected_net_edge_pct)}</td>
        <td>{pct(row.strategy_net_return_1d_pct)}</td><td>{pct(row.strategy_net_return_5d_pct)}</td><td>{pct(row.strategy_net_return_20d_pct)}</td><td>{row.quality_flag ?? "—"}</td>
      </tr>)}
      {!journal.length && <tr><td colSpan={13}>Dziennik jest jeszcze pusty.</td></tr>}
    </tbody></table></div>
  </div>;
}
