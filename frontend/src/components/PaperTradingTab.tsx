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
  const selectedCurrency = selected?.currency ?? "USD";
  const currencies = Array.from(new Set([
    "PLN",
    "USD",
    ...assets.map((asset) => asset.currency).filter(Boolean),
  ])).sort();
  const [currency, setCurrency] = useState(selectedCurrency);
  const storageKey = `mstock-paper-account-${currency}`;
  const [account, setAccount] = useState<PaperAccount | null>(null);
  const [journal, setJournal] = useState<PaperJournal>(emptyJournal);
  const [initialCash, setInitialCash] = useState("16000");
  const [amounts, setAmounts] = useState(["1000", "10000", "5000"]);
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
    if (snapshot.strategy?.buckets.length) {
      setAmounts(snapshot.strategy.buckets.map((bucket) => String(bucket.initial_amount)));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setAccount(null);
    setJournal(emptyJournal);
    setMessage("");
    async function restore() {
      const stored = Number(window.localStorage.getItem(storageKey));
      if (stored > 0) {
        try {
          const snapshot = await api.paperAccount(stored);
          if (snapshot.currency === currency) {
            if (!cancelled) await refresh(stored);
            return;
          }
          window.localStorage.removeItem(storageKey);
        } catch {
          window.localStorage.removeItem(storageKey);
        }
      }
      try {
        const accounts = await api.paperAccounts(currency);
        const snapshot = accounts.find((item) => item.name === `paper-${currency.toLowerCase()}`) ?? accounts[0];
        if (!snapshot || cancelled) return;
        window.localStorage.setItem(`mstock-paper-account-${snapshot.currency}`, String(snapshot.id));
        await refresh(snapshot.id);
      } catch {
        // Brak istniejącego rachunku — pokaż formularz tworzenia.
      }
    }
    void restore();
    return () => { cancelled = true; };
  }, [refresh, storageKey]);

  useEffect(() => {
    if (!account) return;
    const update = () => { void refresh(account.id); };
    const interval = window.setInterval(update, 60_000);
    const onVisibility = () => { if (document.visibilityState === "visible") update(); };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [account?.id, refresh]);

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

  function changeAmount(index: number, value: string) {
    setAmounts((current) => current.map((amount, i) => i === index ? value : amount));
  }

  async function allocateRecommendations() {
    if (!account) return;
    const parsed = amounts.map(Number);
    setBusy(true); setMessage("");
    try {
      const result = await api.allocatePaperRecommendations(account.id, parsed);
      setAccount(result.account);
      setJournal(await api.paperJournal(account.id));
      setMessage(
        result.allocations.length
          ? `Strategia działa w tle. Otwarto ${result.allocations.length} z ${parsed.length} pozycji.`
          : "Strategia działa w tle i czeka na odpowiednie rekomendacje KUP.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally { setBusy(false); }
  }

  async function toggleStrategy() {
    if (!account?.strategy) return;
    setBusy(true); setMessage("");
    try {
      await api.setPaperStrategyActive(account.id, !account.strategy.active);
      await refresh(account.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally { setBusy(false); }
  }

  const parsedAmounts = amounts.map(Number);
  const amountsValid = parsedAmounts.every((amount) => Number.isFinite(amount) && amount > 0);
  const amountsTotal = amountsValid ? parsedAmounts.reduce((sum, amount) => sum + amount, 0) : 0;

  const card: React.CSSProperties = {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, padding: 16,
  };
  const accountCurrency = account?.currency ?? currency;
  const selectedMatchesAccount = !selected || selected.currency === accountCurrency;

  return (
    <div style={{ padding: "16px 0" }}>
      <h2 style={{ marginTop: 0 }}>Paper trading</h2>
      <p style={{ color: "var(--text-3)", fontSize: 13 }}>
        Automatyczna symulacja działa na serwerze także po zamknięciu strony. Co godzinę reaguje na rekomendacje,
        uwzględnia prowizję i poślizg oraz blokuje transakcje przy niepoprawnych danych OHLCV.
        Nowe wejście wymaga zamkniętej świecy dziennej i dwóch kolejnych zgodnych cykli.
      </p>

      <div style={{ ...card, marginBottom: 14 }}>
        <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 8 }}>Rachunek i rynek</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {currencies.map((value) => (
            <button
              key={value}
              type="button"
              disabled={busy}
              onClick={() => setCurrency(value)}
              aria-pressed={currency === value}
              style={currency === value ? { borderColor: "var(--accent)", color: "var(--accent)" } : undefined}
            >
              {value === "PLN" ? "GPW · PLN" : value === "USD" ? "Globalne i ETF · USD" : value}
            </button>
          ))}
        </div>
        <div style={{ color: "var(--text-3)", fontSize: 12, marginTop: 8 }}>
          Konta mają oddzielny kapitał, pozycje, koszyki i dzienniki. Aktywne strategie działają równolegle na serwerze.
        </div>
      </div>

      {!account ? (
        <div style={{ ...card, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <strong>Nowe konto {currency === "PLN" ? "GPW" : "globalne"}</strong>
          <label>Kapitał początkowy ({currency}) </label>
          <input type="number" min="1" value={initialCash} onChange={(e) => setInitialCash(e.target.value)} />
          <button disabled={busy || Number(initialCash) <= 0} onClick={createAccount}>Utwórz konto {currency}</button>
        </div>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
            {[
              ["Kapitał", money(account.equity, accountCurrency)],
              ["Gotówka", money(account.cash, accountCurrency)],
              ["Wartość pozycji", money(account.market_value, accountCurrency)],
              ["Wynik", `${account.total_return_pct >= 0 ? "+" : ""}${account.total_return_pct.toFixed(2)}%`],
              ["Niezrealizowany P/L", money(account.unrealized_pnl, accountCurrency)],
            ].map(([label, value]) => <div key={label} style={card}><small style={{ color: "var(--text-3)" }}>{label}</small><div style={{ fontWeight: 700, marginTop: 5 }}>{value}</div></div>)}
          </div>

          {!account.strategy ? <div style={{ ...card, marginTop: 14 }}>
            <h3 style={{ marginTop: 0, marginBottom: 6 }}>Automatyczna inwestycja według rekomendacji</h3>
            <p style={{ color: "var(--text-3)", fontSize: 13, marginTop: 0 }}>
              Każda kwota zostanie przeznaczona na inne, najwyżej ocenione aktywo z rekomendacją KUP w walucie {accountCurrency}.
              Jeśli dobrych kandydatów będzie mniej, niewykorzystana kwota pozostanie w gotówce.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
              {amounts.map((amount, index) => (
                <label key={index} style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  <span style={{ fontSize: 12, color: "var(--text-3)" }}>Pozycja {index + 1} ({accountCurrency})</span>
                  <span style={{ display: "flex", gap: 6 }}>
                    <input
                      aria-label={`Kwota pozycji ${index + 1}`}
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={amount}
                      onChange={(event) => changeAmount(index, event.target.value)}
                      style={{ minWidth: 0, width: "100%" }}
                    />
                    {amounts.length > 1 && <button type="button" onClick={() => setAmounts((current) => current.filter((_, i) => i !== index))}>×</button>}
                  </span>
                </label>
              ))}
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 12 }}>
              <button type="button" disabled={amounts.length >= 20} onClick={() => setAmounts((current) => [...current, "1000"])}>+ Dodaj kwotę</button>
              <strong>Suma: {money(amountsTotal, accountCurrency)}</strong>
              <button
                type="button"
                disabled={busy || !amountsValid || amountsTotal > account.cash}
                onClick={allocateRecommendations}
              >
                Inwestuj według rekomendacji
              </button>
              {amountsTotal > account.cash && <span style={{ color: "#ef4444", fontSize: 13 }}>Za mało gotówki na podane kwoty.</span>}
            </div>
          </div> : <div style={{ ...card, marginTop: 14 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div>
                <h3 style={{ margin: 0 }}>Automatyczna strategia</h3>
                <div style={{ color: account.strategy.active ? "#16a34a" : "#b45309", fontWeight: 700, marginTop: 5 }}>
                  {account.strategy.active ? "● AKTYWNA — działa w tle" : "● WSTRZYMANA"}
                </div>
              </div>
              <button type="button" disabled={busy} onClick={toggleStrategy}>
                {account.strategy.active ? "Wstrzymaj" : "Wznów"}
              </button>
            </div>
            <p style={{ color: "var(--text-3)", fontSize: 13 }}>
              {account.strategy.last_message || "Oczekuje na cykl"}
              {account.strategy.last_run_at && <> · ostatni cykl {new Date(account.strategy.last_run_at).toLocaleString("pl-PL")}</>}
            </p>
            <div style={{ overflowX: "auto" }}><table><thead><tr><th>Koszyk</th><th>Kwota początkowa</th><th>Stan</th><th>Sygnał</th><th>Aktywo</th><th>Ilość</th><th>Gotówka</th><th>Wartość</th><th>Wynik</th></tr></thead><tbody>
              {account.strategy.buckets.map((bucket) => <tr key={bucket.id}>
                <td>{bucket.ordinal}</td>
                <td>{money(bucket.initial_amount, accountCurrency)}</td>
                <td>{bucket.status === "position" ? "Pozycja" : bucket.signal_status === "confirming" ? "Potwierdzanie" : "Oczekuje"}</td>
                <td title={bucket.signal_message} style={{
                  color: bucket.signal_status === "entry_active" ? "#16a34a"
                    : bucket.signal_status === "exit_signal" ? "#dc2626"
                    : bucket.signal_status === "entry_expired" ? "#b45309"
                    : "var(--text-3)",
                  maxWidth: 260,
                }}>{bucket.signal_message}</td>
                <td>{(bucket.asset_id ?? bucket.pending_asset_id)?.toUpperCase() ?? "—"}</td>
                <td>{bucket.quantity ? bucket.quantity.toLocaleString("pl-PL", { maximumFractionDigits: 8 }) : "—"}</td>
                <td>{money(bucket.cash, accountCurrency)}</td>
                <td>{money(bucket.value, accountCurrency)}</td>
                <td style={{ color: bucket.return_pct >= 0 ? "#16a34a" : "#dc2626" }}>{bucket.return_pct >= 0 ? "+" : ""}{bucket.return_pct.toFixed(2)}%</td>
              </tr>)}
            </tbody></table></div>
          </div>}

          {!account.strategy && <div style={{ ...card, marginTop: 14, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <strong>{selected?.symbol ?? selectedAssetId}</strong>
            <input type="number" min="0.000001" step="any" value={quantity} onChange={(e) => setQuantity(e.target.value)} style={{ width: 110 }} />
            <button disabled={busy || Number(quantity) <= 0 || !selectedMatchesAccount} onClick={() => place("buy")}>Kup</button>
            <button disabled={busy || Number(quantity) <= 0 || !selectedMatchesAccount} onClick={() => place("sell")}>Sprzedaj</button>
            {!selectedMatchesAccount && <span style={{ color: "#b45309", fontSize: 13 }}>
              Wybrane aktywo jest w {selected?.currency}; przełącz rachunek na tę walutę.
            </span>}
            {message && <span style={{ color: "var(--text-2)", fontSize: 13 }}>{message}</span>}
          </div>}

          {account.strategy && message && <p style={{ color: "var(--text-2)", fontSize: 13 }}>{message}</p>}

          <h3>Pozycje</h3>
          <div style={{ overflowX: "auto" }}><table><thead><tr><th>Aktywo</th><th>Ilość</th><th>Śr. cena</th><th>Ostatnia</th><th>P/L</th></tr></thead><tbody>
            {account.positions.map((position) => <tr key={position.asset_id}><td>{position.asset_id.toUpperCase()}</td><td>{position.quantity}</td><td>{money(position.avg_price, accountCurrency)}</td><td>{money(position.last_price, accountCurrency)}</td><td>{money(position.unrealized_pnl, accountCurrency)}</td></tr>)}
            {!account.positions.length && <tr><td colSpan={5}>Brak otwartych pozycji.</td></tr>}
          </tbody></table></div>

          <h3>Dziennik zleceń</h3>
          <div style={{ overflowX: "auto" }}><table><thead><tr><th>Czas</th><th>Aktywo</th><th>Strona</th><th>Ilość</th><th>Status</th><th>Cena</th><th>Koszt</th></tr></thead><tbody>
            {journal.orders.map((order) => <tr key={order.id}><td>{new Date(order.submitted_at).toLocaleString("pl-PL")}</td><td>{order.asset_id.toUpperCase()}</td><td>{order.side === "buy" ? "KUP" : "SPRZEDAJ"}</td><td>{order.quantity}</td><td>{order.status}</td><td>{order.fill_price == null ? "—" : money(order.fill_price, accountCurrency)}</td><td>{money(order.commission + order.slippage, accountCurrency)}</td></tr>)}
            {!journal.orders.length && <tr><td colSpan={7}>Dziennik jest pusty.</td></tr>}
          </tbody></table></div>
        </>
      )}
      {!account && message && <p style={{ color: "#ef4444" }}>{message}</p>}
    </div>
  );
}
