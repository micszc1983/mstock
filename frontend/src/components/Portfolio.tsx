import { useEffect, useRef, useState } from "react";
import { Send, Download, Plus, Trash2, Save, Pencil, X } from "lucide-react";
import type { Asset } from "../lib/types";
import "./Portfolio.css";

type Position = {
  asset_id: string;
  quantity: number;
  avg_buy_price: number | null;
  purchase_date: string | null;
  invested_amount: number | null;
  cost_currency: "PLN";
  updated_at: string;
};

type EditDraft = {
  asset_id: string;
  purchase_date: string;
  quantity: string;
  avg_buy_price: string;
};

type RecData = {
  recommendation: string | null;
  ml_prediction: string | null;
  forecast_dir_5d: string | null;
  forecast_dir_20d: string | null;
  last_price: number | null;
  currency: string;
  intraday_signal: "BUY" | "SELL" | null;
};

type PortfolioValuation = {
  asset_id: string;
  source_currency: string;
  fx_rate_to_pln: number;
  last_price_source: number | null;
  last_price_pln: number | null;
  current_value_pln: number | null;
};

type Props = {
  apiBase: string;
  assets: Asset[];
};

function signalDot(rec: string | null, ml: string | null, f5: string | null, f20: string | null) {
  const allGreen = rec === "KUP" && ml === "up" && f5 === "up" && f20 === "up";
  const allRed   = rec === "SPRZEDAJ" && ml === "down" && f5 === "down" && f20 === "down";
  if (allGreen) return "🟢";
  if (allRed)   return "🔴";
  return "⚪";
}

function recBadge(rec: string | null) {
  if (rec === "KUP")      return { label: "KUP",      bg: "rgba(22,163,74,0.13)",  color: "#16a34a" };
  if (rec === "SPRZEDAJ") return { label: "SPRZEDAJ", bg: "rgba(220,38,38,0.11)",  color: "#dc2626" };
  if (rec === "TRZYMAJ")  return { label: "TRZYMAJ",  bg: "rgba(217,119,6,0.11)",  color: "#d97706" };
  if (rec === "BRAK TRANSAKCJI") return { label: "BRAK TRANSAKCJI", bg: "rgba(100,116,139,0.10)", color: "#64748b" };
  return { label: "—", bg: "var(--bg-subtle)", color: "var(--text-3)" };
}

function arrowDir(dir: string | null) {
  if (dir === "up")   return <span style={{ color: "#16a34a" }}>▲</span>;
  if (dir === "down") return <span style={{ color: "#dc2626" }}>▼</span>;
  return <span style={{ color: "var(--text-3)" }}>—</span>;
}

function formatPrice(v: number | null, currency: string) {
  if (!v) return "—";
  return `${v.toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function formatValue(qty: number, price: number | null, currency: string) {
  if (!price) return "—";
  return `${(qty * price).toLocaleString("pl-PL", { maximumFractionDigits: 0 })} ${currency}`;
}

function todayLocal() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function errorDetail(payload: unknown, fallback: string) {
  if (
    payload
    && typeof payload === "object"
    && "detail" in payload
    && typeof (payload as { detail?: unknown }).detail === "string"
  ) {
    return (payload as { detail: string }).detail;
  }
  return fallback;
}

export function Portfolio({ apiBase, assets }: Props) {
  const [positions, setPositions]   = useState<Position[]>([]);
  const [recMap, setRecMap]         = useState<Record<string, RecData>>({});
  const [valuationMap, setValuationMap] = useState<Record<string, PortfolioValuation>>({});
  const [loading, setLoading]       = useState(false);
  const [sending, setSending]       = useState(false);
  const [info, setInfo]             = useState<string | null>(null);
  const [editId, setEditId]         = useState<string | null>(null);
  const [editDraft, setEditDraft]   = useState<EditDraft | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [addAssetId, setAddAssetId] = useState("");
  const [addDate, setAddDate]       = useState(todayLocal);
  const [addAmount, setAddAmount]   = useState("");
  const [addPrice, setAddPrice]     = useState("");
  const [adding, setAdding]         = useState(false);
  const infoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function showInfo(msg: string) {
    setInfo(msg);
    if (infoTimer.current) clearTimeout(infoTimer.current);
    infoTimer.current = setTimeout(() => setInfo(null), 4000);
  }

  async function fetchPositions() {
    setLoading(true);
    try {
      const r = await fetch(`${apiBase}/portfolio/positions`);
      if (!r.ok) throw new Error("Nie udało się pobrać portfela.");
      const data: Position[] = await r.json();
      setPositions(data);
      await fetchValuations();
      // Rekomendacje są informacją dodatkową. Nie blokuj nimi wyświetlenia
      // salda i pozycji, bo ich obliczenie może potrwać kilka sekund.
      void fetchRecs(data.map(p => p.asset_id));
    } catch (error) {
      showInfo(error instanceof Error ? error.message : "Nie udało się pobrać portfela.");
    } finally {
      setLoading(false);
    }
  }

  async function fetchValuations() {
    const response = await fetch(`${apiBase}/portfolio/valuations`);
    if (!response.ok) return;
    const rows: PortfolioValuation[] = await response.json();
    setValuationMap(Object.fromEntries(rows.map(row => [row.asset_id, row])));
  }

  async function fetchRecs(ids: string[]) {
    const entries = await Promise.all(ids.map(async id => {
      try {
        const r = await fetch(`${apiBase}/assets/${id}/recommendation`);
        if (!r.ok) return [id, {}] as const;
        const d = await r.json();
        let last_price: number | null = d.last_price ?? null;
        if (!last_price) {
          try {
            const pr = await fetch(`${apiBase}/assets/${id}/prices?limit=5`);
            const pts = await pr.json();
            if (pts.length > 0) last_price = pts[pts.length - 1].close ?? pts[pts.length - 1].price;
          } catch {}
        }
        const asset = assets.find(a => a.id === id);
        let intraday_signal: "BUY" | "SELL" | null = null;
        if (asset?.type === "stock") {
          try {
            const ir = await fetch(`${apiBase}/assets/${id}/intraday/signals?resolution=15`);
            if (ir.ok) {
              const id2 = await ir.json();
              const sigs: Array<{ type: string; strength: number }> = id2.signals ?? [];
              if (sigs.some(s => s.type === "BUY" && s.strength >= 0.6)) intraday_signal = "BUY";
              else if (sigs.some(s => s.type === "SELL" && s.strength >= 0.6)) intraday_signal = "SELL";
            }
          } catch {}
        }
        return [id, {
          recommendation:  d.recommendation ?? null,
          ml_prediction:   d.ml_prediction ?? null,
          forecast_dir_5d: d.forecast_dir_5d ?? null,
          forecast_dir_20d: d.forecast_dir_20d ?? null,
          last_price,
          currency: asset?.currency ?? "USD",
          intraday_signal,
        }] as const;
      } catch {
        return [id, {}] as const;
      }
    }));
    setRecMap(Object.fromEntries(entries) as Record<string, RecData>);
  }

  useEffect(() => { fetchPositions(); }, [apiBase]);
  useEffect(() => () => {
    if (infoTimer.current) clearTimeout(infoTimer.current);
  }, []);

  function beginEdit(position: Position) {
    setEditId(position.asset_id);
    setEditDraft({
      asset_id: position.asset_id,
      purchase_date: position.purchase_date ?? "",
      quantity: String(position.quantity),
      avg_buy_price: position.avg_buy_price === null ? "" : String(position.avg_buy_price),
    });
  }

  function cancelEdit() {
    setEditId(null);
    setEditDraft(null);
  }

  async function saveEditedPosition() {
    if (!editId || !editDraft) return;
    const quantity = Number(editDraft.quantity.replace(",", "."));
    const avgBuyPrice = editDraft.avg_buy_price.trim()
      ? Number(editDraft.avg_buy_price.replace(",", "."))
      : null;
    if (!Number.isFinite(quantity) || quantity <= 0) {
      showInfo("Ilość musi być większa od zera.");
      return;
    }
    if (avgBuyPrice !== null && (!Number.isFinite(avgBuyPrice) || avgBuyPrice <= 0)) {
      showInfo("Średnia cena zakupu musi być większa od zera.");
      return;
    }
    setSavingEdit(true);
    try {
      const r = await fetch(`${apiBase}/portfolio/positions/${editId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          asset_id: editDraft.asset_id,
          quantity,
          avg_buy_price: avgBuyPrice,
          purchase_date: editDraft.purchase_date || null,
        }),
      });
      const payload = await r.json().catch(() => null);
      if (!r.ok) {
        showInfo(errorDetail(payload, "Nie udało się zapisać pozycji."));
        return;
      }
      cancelEdit();
      await fetchPositions();
      showInfo(`Pozycja ${editDraft.asset_id.toUpperCase()} została zaktualizowana.`);
    } catch {
      showInfo("Brak połączenia z backendem — zmiany nie zostały zapisane.");
    } finally {
      setSavingEdit(false);
    }
  }

  async function deletePosition(asset_id: string) {
    if (!window.confirm(`Usunąć ${asset_id.toUpperCase()} z portfela?`)) return;
    const r = await fetch(`${apiBase}/portfolio/positions/${asset_id}`, { method: "DELETE" });
    if (!r.ok) {
      showInfo("Nie udało się usunąć pozycji.");
      return;
    }
    if (editId === asset_id) cancelEdit();
    await fetchPositions();
    showInfo(`Usunięto ${asset_id.toUpperCase()} z portfela.`);
  }

  async function addPosition() {
    if (!addAssetId || !addDate || !addAmount) return;
    const amount = parseFloat(addAmount.replace(",", "."));
    const purchasePrice = addPrice.trim() ? parseFloat(addPrice.replace(",", ".")) : null;
    if (!Number.isFinite(amount) || amount <= 0) {
      showInfo("Kwota zakupu musi być większa od zera.");
      return;
    }
    if (purchasePrice !== null && (!Number.isFinite(purchasePrice) || purchasePrice <= 0)) {
      showInfo("Cena wykonania musi być większa od zera.");
      return;
    }
    setAdding(true);
    try {
      const r = await fetch(`${apiBase}/portfolio/positions/${addAssetId}/historical-purchase`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          purchase_date: addDate,
          invested_amount: amount,
          purchase_price: purchasePrice,
        }),
      });
      const payload = await r.json().catch(() => null);
      if (!r.ok) {
        showInfo(errorDetail(payload, "Nie udało się dodać zakupu."));
        return;
      }
      await fetchPositions();
      const wasExisting = positions.some(position => position.asset_id === addAssetId);
      showInfo(`${wasExisting ? "Dokupiono" : "Dodano"} ${addAssetId.toUpperCase()} — średnia cena została przeliczona.`);
      setAddAssetId("");
      setAddAmount("");
      setAddPrice("");
    } catch {
      showInfo("Brak połączenia z backendem — zakup nie został zapisany.");
    } finally {
      setAdding(false);
    }
  }

  // Sort: SPRZEDAJ → KUP → TRZYMAJ → BRAK TRANSAKCJI
  const sorted = [...positions].sort((a, b) => {
    const order: Record<string, number> = { SPRZEDAJ: 0, KUP: 1, TRZYMAJ: 2, "BRAK TRANSAKCJI": 3 };
    const ra = recMap[a.asset_id]?.recommendation ?? "TRZYMAJ";
    const rb = recMap[b.asset_id]?.recommendation ?? "TRZYMAJ";
    return (order[ra] ?? 2) - (order[rb] ?? 2);
  });

  const summaryByCurrency: Record<string, { invested: number; valuedInvested: number; current: number; missingPrices: number }> = {};
  for (const p of positions) {
    const valuation = valuationMap[p.asset_id];
    const currency = "PLN";
    const invested = p.invested_amount ?? (p.avg_buy_price !== null ? p.quantity * p.avg_buy_price : 0);
    const current = valuation?.current_value_pln ?? null;
    const summary = summaryByCurrency[currency] ?? { invested: 0, valuedInvested: 0, current: 0, missingPrices: 0 };
    summary.invested += invested;
    if (current === null) {
      summary.missingPrices += 1;
    } else {
      summary.current += current;
      summary.valuedInvested += invested;
    }
    summaryByCurrency[currency] = summary;
  }
  const selectedAddPosition = positions.find(position => position.asset_id === addAssetId);
  const editInvestedPreview = editDraft?.avg_buy_price.trim() && editDraft.quantity.trim()
    ? Number(editDraft.avg_buy_price.replace(",", ".")) * Number(editDraft.quantity.replace(",", "."))
    : null;

  return (
    <div className="portfolio-page">
      <div className="portfolio-header">
        <div>
          <h2>Portfel inwestycyjny</h2>
          <p>{positions.length} {positions.length === 1 ? "pozycja" : "pozycji"} · wszystkie wartości w PLN</p>
        </div>
        <div className="portfolio-header-actions">
          <button className="portfolio-btn portfolio-btn-secondary" disabled={positions.length === 0} onClick={async () => {
            const r = await fetch(`${apiBase}/portfolio/preview-report`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ to_email: "dev@coad.pl", recommendations: Object.fromEntries(positions.map(p => [p.asset_id, recMap[p.asset_id] ?? {}])) }),
            });
            if (!r.ok) { showInfo("Błąd generowania PDF"); return; }
            const blob = await r.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a"); link.href = url; link.download = "mstock_portfel.pdf"; link.click();
            URL.revokeObjectURL(url);
          }}><Download size={15} /> PDF</button>
          <button className="portfolio-btn portfolio-btn-primary" disabled={sending || positions.length === 0} onClick={async () => {
            setSending(true);
            try {
              const r = await fetch(`${apiBase}/portfolio/send-report`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ to_email: "dev@coad.pl", recommendations: Object.fromEntries(positions.map(p => [p.asset_id, recMap[p.asset_id] ?? {}])) }),
              });
              const d = await r.json().catch(() => ({}));
              showInfo(r.ok ? "Email wysłany na dev@coad.pl" : `Błąd: ${d.detail ?? "nie udało się wysłać raportu"}`);
            } finally { setSending(false); }
          }}><Send size={15} /> {sending ? "Wysyłanie…" : "Wyślij raport"}</button>
        </div>
      </div>

      {Object.entries(summaryByCurrency).length > 0 && (
        <div className="portfolio-summary-grid">
          {Object.entries(summaryByCurrency).map(([currency, values]) => {
            const profit = values.current - values.valuedInvested;
            const profitPct = values.valuedInvested > 0 ? profit / values.valuedInvested * 100 : null;
            return (
              <div className="portfolio-summary-card" key={currency}>
                <div className="portfolio-summary-title">Portfel {currency}</div>
                <div className="portfolio-summary-value">{values.current.toLocaleString("pl-PL", { maximumFractionDigits: 2 })} {currency}</div>
                <div className="portfolio-summary-meta">Wpłacono {values.invested.toLocaleString("pl-PL", { maximumFractionDigits: 2 })} {currency}</div>
                {values.valuedInvested > 0 && <div className={profit >= 0 ? "portfolio-profit" : "portfolio-loss"}>
                    {profit >= 0 ? "+" : ""}{profit.toLocaleString("pl-PL", { maximumFractionDigits: 2 })} {currency}
                    {profitPct !== null ? ` (${profitPct >= 0 ? "+" : ""}${profitPct.toLocaleString("pl-PL", { maximumFractionDigits: 1 })}%)` : ""}
                  </div>}
                {values.missingPrices > 0 && <div className="portfolio-summary-warning">Bez wyceny: {values.missingPrices}</div>}
              </div>
            );
          })}
        </div>
      )}

      {info && <div className="portfolio-notice" role="status">{info}</div>}

      <section className="portfolio-panel">
        <div className="portfolio-panel-heading">
          <div><strong>{selectedAddPosition ? "Dokup aktywo" : "Dodaj zakup"}</strong><span>Nowy zakup istniejącego aktywa przeliczy średnią cenę.</span></div>
        </div>
        <div className="portfolio-form-grid portfolio-add-grid">
          <label className="portfolio-field portfolio-field-wide"><span>Aktywo</span>
            <select value={addAssetId} onChange={e => setAddAssetId(e.target.value)}>
              <option value="">— wybierz aktywo —</option>
              {assets.map(a => <option key={a.id} value={a.id}>{a.symbol} — {a.name}{positions.some(p => p.asset_id === a.id) ? " (w portfelu)" : ""}</option>)}
            </select>
          </label>
          <label className="portfolio-field"><span>Data zakupu</span><input type="date" max={todayLocal()} value={addDate} onChange={e => setAddDate(e.target.value)} /></label>
          <label className="portfolio-field"><span>Kwota w PLN</span><input type="number" min="0" step="any" inputMode="decimal" placeholder="np. 5000 zł" value={addAmount} onChange={e => setAddAmount(e.target.value)} /></label>
          <label className="portfolio-field"><span>Cena za sztukę w PLN <em>opcjonalnie</em></span><input type="number" min="0" step="any" inputMode="decimal" placeholder="z potwierdzenia" value={addPrice} onChange={e => setAddPrice(e.target.value)} /></label>
          <button className="portfolio-btn portfolio-btn-primary portfolio-form-action" onClick={addPosition} disabled={!addAssetId || !addDate || !addAmount || adding}>
            <Plus size={15} /> {adding ? "Zapisywanie…" : selectedAddPosition ? "Dokup" : "Dodaj"}
          </button>
        </div>
        <div className="portfolio-help">Wszystkie kwoty zakupu podajesz w złotówkach. Bez ceny wykonania aplikacja przeliczy cenę zamknięcia kursem NBP z dnia zakupu.</div>
      </section>

      {editId && editDraft && (
        <section className="portfolio-panel portfolio-edit-panel">
          <div className="portfolio-panel-heading">
            <div><strong>Edytuj pozycję</strong><span>Zmiana zapisze całą pozycję i automatycznie przeliczy zainwestowaną kwotę.</span></div>
            <button className="portfolio-icon-btn" onClick={cancelEdit} aria-label="Zamknij edycję"><X size={17} /></button>
          </div>
          <div className="portfolio-form-grid portfolio-edit-grid">
            <label className="portfolio-field portfolio-field-wide"><span>Aktywo</span>
              <select value={editDraft.asset_id} onChange={e => setEditDraft({ ...editDraft, asset_id: e.target.value })}>
                {assets.map(a => <option key={a.id} value={a.id}>{a.symbol} — {a.name}</option>)}
              </select>
            </label>
            <label className="portfolio-field"><span>Data pierwszego zakupu</span><input type="date" max={todayLocal()} value={editDraft.purchase_date} onChange={e => setEditDraft({ ...editDraft, purchase_date: e.target.value })} /></label>
            <label className="portfolio-field"><span>Liczba sztuk</span><input type="number" min="0" step="any" inputMode="decimal" value={editDraft.quantity} onChange={e => setEditDraft({ ...editDraft, quantity: e.target.value })} /></label>
            <label className="portfolio-field"><span>Średnia cena zakupu w PLN</span><input type="number" min="0" step="any" inputMode="decimal" value={editDraft.avg_buy_price} onChange={e => setEditDraft({ ...editDraft, avg_buy_price: e.target.value })} /></label>
            <div className="portfolio-edit-preview"><span>Zainwestowano po zmianie</span><strong>{Number.isFinite(editInvestedPreview) && editInvestedPreview !== null ? editInvestedPreview.toLocaleString("pl-PL", { maximumFractionDigits: 2 }) : "—"} PLN</strong></div>
          </div>
          <div className="portfolio-edit-actions">
            <button className="portfolio-btn portfolio-btn-secondary" onClick={cancelEdit}>Anuluj</button>
            <button className="portfolio-btn portfolio-btn-primary" onClick={saveEditedPosition} disabled={savingEdit}><Save size={15} /> {savingEdit ? "Zapisywanie…" : "Zapisz zmiany"}</button>
          </div>
        </section>
      )}

      {loading ? <div className="portfolio-empty">Ładowanie portfela…</div> : sorted.length === 0 ? (
        <div className="portfolio-empty">Brak pozycji w portfelu. Dodaj pierwszy zakup powyżej.</div>
      ) : (
        <>
          <div className="portfolio-table-wrap">
            <table className="portfolio-table">
              <thead><tr>{["", "Aktywo", "Zakup", "Koszt", "Wartość teraz", "Wynik", "Rekomendacja", "Prognozy", ""].map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
              <tbody>{sorted.map(pos => {
                const asset = assets.find(a => a.id === pos.asset_id);
                const rd = recMap[pos.asset_id] ?? {} as RecData;
                const valuation = valuationMap[pos.asset_id];
                const badge = recBadge(rd.recommendation);
                const currency = "PLN";
                const invested = pos.invested_amount ?? (pos.avg_buy_price !== null ? pos.quantity * pos.avg_buy_price : null);
                const currentValue = valuation?.current_value_pln ?? null;
                const currentPrice = valuation?.last_price_pln ?? null;
                const profit = invested !== null && currentValue !== null ? currentValue - invested : null;
                const profitPct = profit !== null && invested && invested > 0 ? profit / invested * 100 : null;
                return <tr key={pos.asset_id} className={editId === pos.asset_id ? "portfolio-row-editing" : ""}>
                  <td className="portfolio-signal">{signalDot(rd.recommendation, rd.ml_prediction, rd.forecast_dir_5d, rd.forecast_dir_20d)}</td>
                  <td><strong>{asset?.symbol ?? pos.asset_id.toUpperCase()}</strong><span>{asset?.name ?? pos.asset_id}</span></td>
                  <td><strong>{pos.quantity.toLocaleString("pl-PL", { maximumFractionDigits: 6 })} szt.</strong><span>{pos.purchase_date ? new Date(`${pos.purchase_date}T12:00:00`).toLocaleDateString("pl-PL") : "brak daty"}</span></td>
                  <td><strong>{formatPrice(pos.avg_buy_price, currency)}</strong><span>{invested !== null ? `${invested.toLocaleString("pl-PL", { maximumFractionDigits: 2 })} ${currency}` : "brak ceny zakupu"}</span></td>
                  <td><strong>{formatValue(pos.quantity, currentPrice, currency)}</strong><span>{formatPrice(currentPrice, currency)} / szt.{valuation?.source_currency !== "PLN" && valuation?.fx_rate_to_pln ? ` · 1 ${valuation.source_currency} = ${valuation.fx_rate_to_pln.toFixed(4)} PLN` : ""}</span></td>
                  <td className={profit === null ? "" : profit >= 0 ? "portfolio-profit" : "portfolio-loss"}><strong>{profit !== null ? `${profit >= 0 ? "+" : ""}${profit.toLocaleString("pl-PL", { maximumFractionDigits: 2 })} ${currency}` : "—"}</strong><span>{profitPct !== null ? `${profitPct >= 0 ? "+" : ""}${profitPct.toLocaleString("pl-PL", { maximumFractionDigits: 1 })}%` : "brak danych"}</span></td>
                  <td><span className="portfolio-rec-badge" style={{ background: badge.bg, color: badge.color }}>{badge.label}</span></td>
                  <td><div className="portfolio-forecast"><span>ML {arrowDir(rd.ml_prediction)}</span><span>5d {arrowDir(rd.forecast_dir_5d)}</span><span>20d {arrowDir(rd.forecast_dir_20d)}</span><span>Intra {arrowDir(rd.intraday_signal === "BUY" ? "up" : rd.intraday_signal === "SELL" ? "down" : null)}</span></div></td>
                  <td><div className="portfolio-row-actions"><button className="portfolio-icon-btn" onClick={() => beginEdit(pos)} title="Edytuj całą pozycję"><Pencil size={15} /></button><button className="portfolio-icon-btn portfolio-delete-btn" onClick={() => deletePosition(pos.asset_id)} title="Usuń pozycję"><Trash2 size={15} /></button></div></td>
                </tr>;
              })}</tbody>
            </table>
          </div>

          <div className="portfolio-mobile-list">{sorted.map(pos => {
            const asset = assets.find(a => a.id === pos.asset_id);
            const rd = recMap[pos.asset_id] ?? {} as RecData;
            const valuation = valuationMap[pos.asset_id];
            const badge = recBadge(rd.recommendation);
            const currency = "PLN";
            const invested = pos.invested_amount ?? (pos.avg_buy_price !== null ? pos.quantity * pos.avg_buy_price : null);
            const currentValue = valuation?.current_value_pln ?? null;
            const currentPrice = valuation?.last_price_pln ?? null;
            const profit = invested !== null && currentValue !== null ? currentValue - invested : null;
            const profitPct = profit !== null && invested && invested > 0 ? profit / invested * 100 : null;
            return <article className={`portfolio-mobile-card ${editId === pos.asset_id ? "portfolio-row-editing" : ""}`} key={pos.asset_id}>
              <div className="portfolio-mobile-head"><div className="portfolio-signal">{signalDot(rd.recommendation, rd.ml_prediction, rd.forecast_dir_5d, rd.forecast_dir_20d)}</div><div><strong>{asset?.symbol ?? pos.asset_id.toUpperCase()}</strong><span>{asset?.name ?? pos.asset_id}</span></div><span className="portfolio-rec-badge" style={{ background: badge.bg, color: badge.color }}>{badge.label}</span></div>
              <div className="portfolio-mobile-metrics"><div><span>Wartość</span><strong>{formatValue(pos.quantity, currentPrice, currency)}</strong></div><div><span>Wynik</span><strong className={profit === null ? "" : profit >= 0 ? "portfolio-profit" : "portfolio-loss"}>{profit !== null ? `${profit >= 0 ? "+" : ""}${profit.toLocaleString("pl-PL", { maximumFractionDigits: 2 })} ${currency}` : "—"}</strong><small>{profitPct !== null ? `${profitPct >= 0 ? "+" : ""}${profitPct.toLocaleString("pl-PL", { maximumFractionDigits: 1 })}%` : ""}</small></div></div>
              <div className="portfolio-mobile-details"><span>{pos.quantity.toLocaleString("pl-PL", { maximumFractionDigits: 6 })} szt. × {formatPrice(pos.avg_buy_price, currency)}</span><span>{pos.purchase_date ? new Date(`${pos.purchase_date}T12:00:00`).toLocaleDateString("pl-PL") : "brak daty zakupu"}</span><span>Wpłacono: {invested !== null ? `${invested.toLocaleString("pl-PL", { maximumFractionDigits: 2 })} ${currency}` : "—"}</span>{valuation?.source_currency !== "PLN" && valuation?.fx_rate_to_pln ? <span>Kurs: 1 {valuation.source_currency} = {valuation.fx_rate_to_pln.toFixed(4)} PLN</span> : null}</div>
              <div className="portfolio-mobile-footer"><div className="portfolio-forecast"><span>ML {arrowDir(rd.ml_prediction)}</span><span>5d {arrowDir(rd.forecast_dir_5d)}</span><span>20d {arrowDir(rd.forecast_dir_20d)}</span><span>Intra {arrowDir(rd.intraday_signal === "BUY" ? "up" : rd.intraday_signal === "SELL" ? "down" : null)}</span></div><div className="portfolio-row-actions"><button className="portfolio-btn portfolio-btn-secondary" onClick={() => beginEdit(pos)}><Pencil size={14} /> Edytuj</button><button className="portfolio-icon-btn portfolio-delete-btn" onClick={() => deletePosition(pos.asset_id)} aria-label="Usuń pozycję"><Trash2 size={15} /></button></div></div>
            </article>;
          })}</div>
        </>
      )}
    </div>
  );
}
