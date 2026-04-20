import { useEffect, useRef, useState } from "react";
import { Send, Download, Plus, Trash2, Save } from "lucide-react";
import type { Asset } from "../lib/types";

type Position = {
  asset_id: string;
  quantity: number;
};

type RecData = {
  recommendation: string | null;
  ml_prediction: string | null;
  forecast_dir_5d: string | null;
  forecast_dir_20d: string | null;
  last_price: number | null;
  currency: string;
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

export function Portfolio({ apiBase, assets }: Props) {
  const [positions, setPositions]   = useState<Position[]>([]);
  const [recMap, setRecMap]         = useState<Record<string, RecData>>({});
  const [loading, setLoading]       = useState(false);
  const [sending, setSending]       = useState(false);
  const [info, setInfo]             = useState<string | null>(null);
  const [editId, setEditId]         = useState<string | null>(null);
  const [editQty, setEditQty]       = useState<Record<string, string>>({});
  const [addAssetId, setAddAssetId] = useState("");
  const [addQty, setAddQty]         = useState("");
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
      const data: Position[] = await r.json();
      setPositions(data);
      fetchRecs(data.map(p => p.asset_id));
    } finally {
      setLoading(false);
    }
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
        return [id, {
          recommendation:  d.recommendation ?? null,
          ml_prediction:   d.ml_prediction ?? null,
          forecast_dir_5d: d.forecast_dir_5d ?? null,
          forecast_dir_20d: d.forecast_dir_20d ?? null,
          last_price,
          currency: asset?.currency ?? "USD",
        }] as const;
      } catch {
        return [id, {}] as const;
      }
    }));
    setRecMap(Object.fromEntries(entries) as Record<string, RecData>);
  }

  useEffect(() => { fetchPositions(); }, [apiBase]);

  async function savePosition(asset_id: string, quantity: number) {
    await fetch(`${apiBase}/portfolio/positions/${asset_id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity, avg_buy_price: null }),
    });
    await fetchPositions();
    showInfo(`Pozycja ${asset_id.toUpperCase()} zapisana.`);
  }

  async function deletePosition(asset_id: string) {
    await fetch(`${apiBase}/portfolio/positions/${asset_id}`, { method: "DELETE" });
    await fetchPositions();
    showInfo(`Usunięto ${asset_id.toUpperCase()} z portfela.`);
  }

  async function addPosition() {
    if (!addAssetId || !addQty) return;
    const qty = parseFloat(addQty.replace(",", "."));
    if (isNaN(qty) || qty <= 0) { showInfo("Nieprawidłowa ilość."); return; }
    await savePosition(addAssetId, qty);
    setAddAssetId(""); setAddQty("");
  }

  // Sort: SPRZEDAJ → KUP → TRZYMAJ
  const sorted = [...positions].sort((a, b) => {
    const order: Record<string, number> = { SPRZEDAJ: 0, KUP: 1, TRZYMAJ: 2 };
    const ra = recMap[a.asset_id]?.recommendation ?? "TRZYMAJ";
    const rb = recMap[b.asset_id]?.recommendation ?? "TRZYMAJ";
    return (order[ra] ?? 2) - (order[rb] ?? 2);
  });

  const totalByC: Record<string, number> = {};
  for (const p of positions) {
    const rd = recMap[p.asset_id];
    if (!rd?.last_price) continue;
    totalByC[rd.currency] = (totalByC[rd.currency] ?? 0) + p.quantity * rd.last_price;
  }

  const assetsNotInPortfolio = assets.filter(a => !positions.some(p => p.asset_id === a.id));

  return (
    <div style={{ padding: "1.2rem 0" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.8rem", marginBottom: "1.2rem", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 700, color: "var(--text-1)" }}>Portfel inwestycyjny</h2>
        <div style={{ flex: 1 }} />
        {Object.entries(totalByC).map(([c, v]) => (
          <span key={c} style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-1)", background: "var(--bg-subtle)", border: "1px solid var(--border)", borderRadius: 6, padding: "3px 10px" }}>
            {v.toLocaleString("pl-PL", { maximumFractionDigits: 0 })} {c}
          </span>
        ))}
        <button onClick={async () => {
          const r = await fetch(`${apiBase}/portfolio/preview-report`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ to_email: "dev@coad.pl", recommendations: Object.fromEntries(positions.map(p => [p.asset_id, recMap[p.asset_id] ?? {}])) }),
          });
          if (!r.ok) { showInfo("Błąd generowania PDF"); return; }
          const blob = await r.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a"); a.href = url; a.download = "mstock_portfel.pdf"; a.click();
          URL.revokeObjectURL(url);
        }} style={{ display: "flex", alignItems: "center", gap: "0.4rem", padding: "5px 12px", borderRadius: 7, border: "1px solid var(--border)", background: "var(--bg-subtle)", cursor: "pointer", fontSize: "0.83rem", color: "var(--text-2)" }}>
          <Download size={14} /> Pobierz PDF
        </button>
        <button onClick={async () => {
          setSending(true);
          try {
            const r = await fetch(`${apiBase}/portfolio/send-report`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ to_email: "dev@coad.pl", recommendations: Object.fromEntries(positions.map(p => [p.asset_id, recMap[p.asset_id] ?? {}])) }),
            });
            const d = await r.json();
            showInfo(r.ok ? "Email wysłany na dev@coad.pl" : `Błąd: ${d.detail}`);
          } finally { setSending(false); }
        }} disabled={sending || positions.length === 0}
          style={{ display: "flex", alignItems: "center", gap: "0.4rem", padding: "5px 14px", borderRadius: 7, border: "none", background: sending ? "var(--bg-subtle)" : "var(--accent)", cursor: "pointer", fontSize: "0.83rem", color: sending ? "var(--text-3)" : "#fff", fontWeight: 600 }}>
          <Send size={14} /> {sending ? "Wysyłanie…" : "Wyślij raport"}
        </button>
      </div>

      {info && (
        <div style={{ marginBottom: "0.8rem", padding: "8px 14px", borderRadius: 7, background: "var(--bg-subtle)", border: "1px solid var(--border)", fontSize: "0.85rem", color: "var(--text-2)" }}>
          {info}
        </div>
      )}

      {/* Dodaj pozycję */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.2rem", alignItems: "center", padding: "10px 14px", background: "var(--bg-subtle)", border: "1px solid var(--border)", borderRadius: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.82rem", color: "var(--text-3)", fontWeight: 600 }}>Dodaj:</span>
        <select value={addAssetId} onChange={e => setAddAssetId(e.target.value)}
          style={{ padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-card)", color: "var(--text-1)", fontSize: "0.83rem" }}>
          <option value="">— wybierz aktywo —</option>
          {assetsNotInPortfolio.map(a => <option key={a.id} value={a.id}>{a.symbol} — {a.name}</option>)}
        </select>
        <input type="number" placeholder="Ilość" value={addQty} onChange={e => setAddQty(e.target.value)}
          style={{ width: 90, padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-card)", color: "var(--text-1)", fontSize: "0.83rem" }} />
        <button onClick={addPosition} disabled={!addAssetId || !addQty}
          style={{ display: "flex", alignItems: "center", gap: "0.35rem", padding: "4px 14px", borderRadius: 6, border: "none", background: "var(--accent)", color: "#fff", fontSize: "0.83rem", fontWeight: 600, cursor: "pointer" }}>
          <Plus size={13} /> Dodaj
        </button>
      </div>

      {/* Tabela */}
      {loading ? (
        <div style={{ color: "var(--text-3)", padding: "1rem" }}>Ładowanie…</div>
      ) : sorted.length === 0 ? (
        <div style={{ color: "var(--text-3)", padding: "2rem", textAlign: "center", border: "1px dashed var(--border)", borderRadius: 8 }}>
          Brak pozycji w portfelu. Dodaj pierwsze aktywo powyżej.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ background: "var(--bg-subtle)", borderBottom: "2px solid var(--border)" }}>
                {["Sygnał", "Aktywo", "Symbol", "Ilość", "Cena", "Wartość", "Rekomendacja", "ML", "5d", "20d", ""].map((h, i) => (
                  <th key={i} style={{ padding: "7px 10px", textAlign: ["Ilość","Cena","Wartość"].includes(h) ? "right" : "left", fontWeight: 600, fontSize: "0.78rem", color: "var(--text-3)", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((pos, i) => {
                const asset  = assets.find(a => a.id === pos.asset_id);
                const rd     = recMap[pos.asset_id] ?? {} as RecData;
                const dot    = signalDot(rd.recommendation, rd.ml_prediction, rd.forecast_dir_5d, rd.forecast_dir_20d);
                const badge  = recBadge(rd.recommendation);
                const isEdit = editId === pos.asset_id;

                return (
                  <tr key={pos.asset_id} style={{ borderBottom: "1px solid var(--border)", background: i % 2 === 0 ? "var(--bg-card)" : "transparent" }}>
                    <td style={{ padding: "7px 10px", fontSize: "1rem", textAlign: "center" }}>{dot}</td>
                    <td style={{ padding: "7px 10px", fontWeight: 500, whiteSpace: "nowrap" }}>{asset?.name ?? pos.asset_id}</td>
                    <td style={{ padding: "7px 10px", color: "var(--text-3)", fontFamily: "monospace" }}>{asset?.symbol ?? pos.asset_id.toUpperCase()}</td>
                    <td style={{ padding: "7px 10px", textAlign: "right" }}>
                      {isEdit ? (
                        <input type="number" value={editQty[pos.asset_id] ?? String(pos.quantity)}
                          onChange={e => setEditQty(q => ({ ...q, [pos.asset_id]: e.target.value }))}
                          style={{ width: 80, padding: "2px 6px", borderRadius: 5, border: "1px solid var(--accent)", background: "var(--bg-card)", color: "var(--text-1)", fontSize: "0.83rem", textAlign: "right" }} />
                      ) : (
                        <span style={{ fontVariantNumeric: "tabular-nums" }}>{pos.quantity.toLocaleString("pl-PL")}</span>
                      )}
                    </td>
                    <td style={{ padding: "7px 10px", textAlign: "right", color: "var(--text-2)", fontVariantNumeric: "tabular-nums" }}>{formatPrice(rd.last_price ?? null, rd.currency ?? "USD")}</td>
                    <td style={{ padding: "7px 10px", textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{formatValue(pos.quantity, rd.last_price ?? null, rd.currency ?? "USD")}</td>
                    <td style={{ padding: "7px 10px" }}>
                      <span style={{ padding: "2px 8px", borderRadius: 5, background: badge.bg, color: badge.color, fontWeight: 700, fontSize: "0.78rem" }}>{badge.label}</span>
                    </td>
                    <td style={{ padding: "7px 10px", textAlign: "center" }}>{arrowDir(rd.ml_prediction === "up" ? "up" : rd.ml_prediction === "down" ? "down" : null)}</td>
                    <td style={{ padding: "7px 10px", textAlign: "center" }}>{arrowDir(rd.forecast_dir_5d)}</td>
                    <td style={{ padding: "7px 10px", textAlign: "center" }}>{arrowDir(rd.forecast_dir_20d)}</td>
                    <td style={{ padding: "7px 10px", whiteSpace: "nowrap" }}>
                      {isEdit ? (
                        <>
                          <button onClick={async () => {
                            const qty = parseFloat((editQty[pos.asset_id] ?? String(pos.quantity)).replace(",", "."));
                            await savePosition(pos.asset_id, qty);
                            setEditId(null);
                          }} style={{ padding: "3px 8px", borderRadius: 5, border: "none", background: "var(--accent)", color: "#fff", fontSize: "0.78rem", cursor: "pointer", marginRight: 4 }}>
                            <Save size={11} style={{ verticalAlign: "middle" }} /> Zapisz
                          </button>
                          <button onClick={() => setEditId(null)}
                            style={{ padding: "3px 8px", borderRadius: 5, border: "1px solid var(--border)", background: "var(--bg-subtle)", color: "var(--text-2)", fontSize: "0.78rem", cursor: "pointer" }}>
                            Anuluj
                          </button>
                        </>
                      ) : (
                        <>
                          <button onClick={() => { setEditId(pos.asset_id); setEditQty(q => ({ ...q, [pos.asset_id]: String(pos.quantity) })); }}
                            style={{ padding: "3px 8px", borderRadius: 5, border: "1px solid var(--border)", background: "var(--bg-subtle)", color: "var(--text-2)", fontSize: "0.78rem", cursor: "pointer", marginRight: 4 }}>
                            Edytuj
                          </button>
                          <button onClick={() => deletePosition(pos.asset_id)}
                            style={{ padding: "3px 7px", borderRadius: 5, border: "1px solid rgba(220,38,38,0.3)", background: "rgba(220,38,38,0.07)", color: "#dc2626", fontSize: "0.78rem", cursor: "pointer" }}>
                            <Trash2 size={11} />
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
