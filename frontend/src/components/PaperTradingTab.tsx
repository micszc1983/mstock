import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Asset, PaperAccount, PaperJournal } from "../lib/types";

type Props = { assets: Asset[]; selectedAssetId: string };

const emptyJournal: PaperJournal = { orders: [], trades: [] };

function money(value: number, currency: string) {
  return `${value.toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

export function PaperTradingTab({ assets, selectedAssetId }: Props) {
  const selected = assets.find((asset) => asset.id === selectedAssetId);
  const currency = selected?.currency ?? "USD";
  const storageKey = `mstock-paper-account-${currency}`;
  const [account, setAccount] = useState<PaperAccount | null>(null);
  const [journal, setJournal] = useState<PaperJournal>(emptyJournal);
  const [initialCash, setInitialCash] = useState("10000");
  const [quantity, setQuantity] = useState("1");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async (accountId: number) => {
    const [snapshot, entries] = await Promise.all([
      api.paperAccount(accountId),
      api.paperJournal(accountId),
    ]);
    setAccount(snapshot);
    setJournal(entries);
  }, []);

  useEffect(() => {
    setAccount(null);
    setJournal(emptyJournal);
    const stored = Number(window.localStorage.getItem(storageKey));
    if (stored > 0) refresh(stored).catch(() => window.localStorage.removeItem(storageKey));
  }, [refresh, storageKey]);

  async function createAccount() {
    setBusy(true); setMessage("");
    try {
      const snapshot = await api.createPaperAccount(
        `paper-${currency.toLowerCase()}`,
        Number(initialCash),
        currency,
      );
      window.localStorage.setItem(storageKey, String(snapshot.id));
      await refresh(snapshot.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally { setBusy(false); }
  }

  async function place(side: "buy" | "sell") {
    if (!account || !selected) return;
    setBusy(true); setMessage("");
    try {
      const order = await api.placePaperOrder(account.id, selected.id, side, Number(quantity));
      setMessage(order.status === "filled" ? "Zlecenie wykonane." : `Zlecenie odrzucone: ${order.note}`);
      await refresh(account.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally { setBusy(false); }
  }

  const card: React.CSSProperties = {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, padding: 16,
  };

  return (
    <div style={{ padding: "16px 0" }}>
      <h2 style={{ marginTop: 0 }}>Paper trading</h2>
      <p style={{ color: "var(--text-3)", fontSize: 13 }}>
        Wirtualne zlecenia market z prowizją i poślizgiem. Zlecenie jest blokowane, jeśli dane OHLCV są niepoprawne.
      </p>

      {!account ? (
        <div style={{ ...card, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <label>Kapitał początkowy ({currency}) </label>
          <input type="number" min="1" value={initialCash} onChange={(e) => setInitialCash(e.target.value)} />
          <button disabled={busy || Number(initialCash) <= 0} onClick={createAccount}>Utwórz konto</button>
        </div>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
            {[
              ["Kapitał", money(account.equity, currency)],
              ["Gotówka", money(account.cash, currency)],
              ["Wartość pozycji", money(account.market_value, currency)],
              ["Wynik", `${account.total_return_pct >= 0 ? "+" : ""}${account.total_return_pct.toFixed(2)}%`],
              ["Niezrealizowany P/L", money(account.unrealized_pnl, currency)],
            ].map(([label, value]) => <div key={label} style={card}><small style={{ color: "var(--text-3)" }}>{label}</small><div style={{ fontWeight: 700, marginTop: 5 }}>{value}</div></div>)}
          </div>

          <div style={{ ...card, marginTop: 14, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <strong>{selected?.symbol ?? selectedAssetId}</strong>
            <input type="number" min="0.000001" step="any" value={quantity} onChange={(e) => setQuantity(e.target.value)} style={{ width: 110 }} />
            <button disabled={busy || Number(quantity) <= 0} onClick={() => place("buy")}>Kup</button>
            <button disabled={busy || Number(quantity) <= 0} onClick={() => place("sell")}>Sprzedaj</button>
            {message && <span style={{ color: "var(--text-2)", fontSize: 13 }}>{message}</span>}
          </div>

          <h3>Pozycje</h3>
          <div style={{ overflowX: "auto" }}><table><thead><tr><th>Aktywo</th><th>Ilość</th><th>Śr. cena</th><th>Ostatnia</th><th>P/L</th></tr></thead><tbody>
            {account.positions.map((position) => <tr key={position.asset_id}><td>{position.asset_id.toUpperCase()}</td><td>{position.quantity}</td><td>{money(position.avg_price, currency)}</td><td>{money(position.last_price, currency)}</td><td>{money(position.unrealized_pnl, currency)}</td></tr>)}
            {!account.positions.length && <tr><td colSpan={5}>Brak otwartych pozycji.</td></tr>}
          </tbody></table></div>

          <h3>Dziennik zleceń</h3>
          <div style={{ overflowX: "auto" }}><table><thead><tr><th>Czas</th><th>Aktywo</th><th>Strona</th><th>Ilość</th><th>Status</th><th>Cena</th><th>Koszt</th></tr></thead><tbody>
            {journal.orders.map((order) => <tr key={order.id}><td>{new Date(order.submitted_at).toLocaleString("pl-PL")}</td><td>{order.asset_id.toUpperCase()}</td><td>{order.side === "buy" ? "KUP" : "SPRZEDAJ"}</td><td>{order.quantity}</td><td>{order.status}</td><td>{order.fill_price == null ? "—" : money(order.fill_price, currency)}</td><td>{money(order.commission + order.slippage, currency)}</td></tr>)}
            {!journal.orders.length && <tr><td colSpan={7}>Dziennik jest pusty.</td></tr>}
          </tbody></table></div>
        </>
      )}
      {!account && message && <p style={{ color: "#ef4444" }}>{message}</p>}
    </div>
  );
}
