import { useEffect, useState, useCallback } from "react";
import { adminHeaders, api } from "../lib/api";
import type { SmsAlertConfig, AlertRuleConfig } from "../lib/types";

const S = {
  card: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    padding: "18px 20px",
    marginBottom: 16,
  } as React.CSSProperties,
  sectionTitle: {
    color: "var(--text-1)",
    fontWeight: 700,
    fontSize: 15,
    marginBottom: 14,
  } as React.CSSProperties,
  label: {
    color: "var(--text-2)",
    fontSize: 13,
    marginBottom: 4,
    display: "block",
  } as React.CSSProperties,
  input: {
    background: "var(--surface-2, #1e293b)",
    color: "var(--text-1)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "5px 10px",
    fontSize: 13,
    width: 110,
  } as React.CSSProperties,
  desc: {
    color: "var(--text-3)",
    fontSize: 11,
    marginTop: 2,
  } as React.CSSProperties,
};

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      style={{
        width: 44,
        height: 24,
        borderRadius: 12,
        border: "none",
        cursor: "pointer",
        background: value ? "#22c55e" : "#475569",
        position: "relative",
        transition: "background 0.2s",
        flexShrink: 0,
      }}
    >
      <span style={{
        position: "absolute",
        top: 3,
        left: value ? 22 : 3,
        width: 18,
        height: 18,
        borderRadius: "50%",
        background: "#fff",
        transition: "left 0.2s",
      }} />
    </button>
  );
}

function NumInput({ value, onChange, min, max, step = 1 }: {
  value: number; onChange: (v: number) => void;
  min?: number; max?: number; step?: number;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={e => onChange(parseFloat(e.target.value))}
      style={S.input}
    />
  );
}

export function AlertsConfigTab() {
  const [cfg, setCfg] = useState<SmsAlertConfig | null>(null);
  const [draft, setDraft] = useState<SmsAlertConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [testingSms, setTestingSms] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.smsAlertConfig();
      setCfg(data);
      setDraft(JSON.parse(JSON.stringify(data)));
    } catch {
      setMsg({ type: "err", text: "Błąd ładowania konfiguracji" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setMsg(null);
    try {
      await api.saveSmsAlertConfig({
        alert_rules: draft.alert_rules,
        top_picks_sms: draft.top_picks_sms,
        paper_trading_sms: draft.paper_trading_sms,
        portfolio_sell_urgent: draft.portfolio_sell_urgent,
        premarket_gap: draft.premarket_gap,
      });
      setCfg(JSON.parse(JSON.stringify(draft)));
      setMsg({ type: "ok", text: "Zapisano. Zmiany działają natychmiast — bez restartu." });
    } catch {
      setMsg({ type: "err", text: "Błąd zapisu konfiguracji" });
    } finally {
      setSaving(false);
    }
  };

  const testSms = async () => {
    setTestingSms(true);
    setMsg(null);
    try {
      const r = await fetch(`${api.apiBase}/admin/test-sms`, { method: "POST", headers: adminHeaders() });
      const d = await r.json();
      if (d.sent) setMsg({ type: "ok", text: `SMS testowy wysłany na ${d.recipient}` });
      else setMsg({ type: "err", text: d.reason || "SMS niewyslany" });
    } catch {
      setMsg({ type: "err", text: "Błąd połączenia z backendem" });
    } finally {
      setTestingSms(false);
    }
  };

  const setRule = (key: string, field: keyof AlertRuleConfig, value: unknown) => {
    setDraft(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        alert_rules: {
          ...prev.alert_rules,
          [key]: { ...prev.alert_rules[key], [field]: value },
        },
      };
    });
  };

  const setSection = <K extends "top_picks_sms" | "paper_trading_sms" | "portfolio_sell_urgent" | "premarket_gap">(
    section: K,
    field: string,
    value: unknown,
  ) => {
    setDraft(prev => {
      if (!prev) return prev;
      return { ...prev, [section]: { ...prev[section], [field]: value } };
    });
  };

  const hasChanges = JSON.stringify(draft?.alert_rules) !== JSON.stringify(cfg?.alert_rules)
    || JSON.stringify(draft?.top_picks_sms) !== JSON.stringify(cfg?.top_picks_sms)
    || JSON.stringify(draft?.paper_trading_sms) !== JSON.stringify(cfg?.paper_trading_sms)
    || JSON.stringify(draft?.portfolio_sell_urgent) !== JSON.stringify(cfg?.portfolio_sell_urgent)
    || JSON.stringify(draft?.premarket_gap) !== JSON.stringify(cfg?.premarket_gap);

  if (loading) return <div style={{ padding: 32, color: "var(--text-3)" }}>Ładowanie...</div>;
  if (!draft) return <div style={{ padding: 32, color: "#ef4444" }}>Błąd ładowania konfiguracji.</div>;

  const status = draft.sms_status;

  return (
    <div style={{ padding: "0 16px 40px", maxWidth: 860 }}>

      {/* Status SMS */}
      <div style={S.card}>
        <div style={S.sectionTitle}>Status SMS</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 24 }}>
          {[
            { label: "SMS włączony", value: status.enabled ? "TAK" : "NIE", ok: status.enabled },
            { label: "Port modemu", value: status.port },
            { label: "Numer odbiorcy", value: status.recipient },
            { label: "Finnhub API", value: status.finnhub_configured ? "skonfigurowany" : "brak klucza", ok: status.finnhub_configured },
          ].map(({ label, value, ok }) => (
            <div key={label}>
              <div style={S.desc}>{label}</div>
              <div style={{ color: ok === false ? "#ef4444" : ok === true ? "#22c55e" : "var(--text-1)", fontWeight: 600, fontSize: 13 }}>{value}</div>
            </div>
          ))}
          <div style={{ marginLeft: "auto" }}>
            <button
              onClick={testSms}
              disabled={testingSms || !status.enabled}
              style={{
                background: "#0f766e", color: "#fff", border: "none", borderRadius: 7,
                padding: "7px 16px", cursor: "pointer", fontSize: 13, fontWeight: 600,
                opacity: (!status.enabled || testingSms) ? 0.5 : 1,
              }}
            >
              {testingSms ? "Wysyłam..." : "Wyślij testowy SMS"}
            </button>
          </div>
        </div>
        {!status.enabled && (
          <div style={{ marginTop: 10, color: "#f59e0b", fontSize: 12 }}>
            SMS jest wyłączony. Ustaw <code>SMS_ENABLED=true</code> w pliku backend/.env i zrestartuj backend.
          </div>
        )}
      </div>

      {/* Reguły alert engine */}
      <div style={S.card}>
        <div style={S.sectionTitle}>Reguły alertów (alert engine)</div>
        <div style={{ display: "grid", gap: 2 }}>
          {/* Nagłówek */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 44px 120px 120px", gap: 8, padding: "4px 0 8px", borderBottom: "1px solid var(--border)" }}>
            {["Reguła", "Aktywna", "Cooldown (min)", "Próg"].map(h => (
              <div key={h} style={{ color: "var(--text-3)", fontSize: 11, fontWeight: 600 }}>{h}</div>
            ))}
          </div>

          {Object.entries(draft.alert_rules).map(([key, rule]) => {
            const label = draft.alert_rule_labels?.[key] ?? key;
            const desc = draft.alert_rule_descriptions?.[key] ?? "";
            const thresholdLabel = draft.threshold_labels?.[key];

            return (
              <div
                key={key}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 44px 120px 120px",
                  gap: 8,
                  padding: "10px 0",
                  borderBottom: "1px solid var(--border)",
                  opacity: rule.enabled ? 1 : 0.45,
                }}
              >
                <div>
                  <div style={{ color: "var(--text-1)", fontSize: 13, fontWeight: 600 }}>{label}</div>
                  <div style={S.desc}>{desc}</div>
                </div>
                <div style={{ display: "flex", alignItems: "center" }}>
                  <Toggle value={rule.enabled} onChange={v => setRule(key, "enabled", v)} />
                </div>
                <div style={{ display: "flex", alignItems: "center" }}>
                  <NumInput
                    value={rule.cooldown_minutes}
                    onChange={v => setRule(key, "cooldown_minutes", v)}
                    min={5}
                    max={10080}
                    step={30}
                  />
                </div>
                <div style={{ display: "flex", alignItems: "center" }}>
                  {thresholdLabel && rule.threshold !== undefined ? (
                    <div>
                      <NumInput
                        value={rule.threshold}
                        onChange={v => setRule(key, "threshold", v)}
                        step={key === "ml_bearish_divergence" ? 0.05 : 1}
                        min={key === "price_drop_session" ? -50 : 0}
                        max={key === "ml_bearish_divergence" ? 1 : 100}
                      />
                      <div style={S.desc}>{thresholdLabel}</div>
                    </div>
                  ) : (
                    <span style={{ color: "var(--text-3)", fontSize: 12 }}>—</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SMS specjalne */}
      <div style={S.card}>
        <div style={S.sectionTitle}>SMS specjalne</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Top Picks */}
          <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
            <div style={{ flex: 1 }}>
              <div style={{ color: "var(--text-1)", fontSize: 13, fontWeight: 600 }}>SMS: nowe Top Pick</div>
              <div style={S.desc}>Wysyła SMS gdy nowe aktywo pojawi się w zakładce Top Picks.</div>
            </div>
            <Toggle value={draft.top_picks_sms.enabled} onChange={v => setSection("top_picks_sms", "enabled", v)} />
          </div>

          {/* Paper trading */}
          <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
            <div style={{ flex: 1 }}>
              <div style={{ color: "var(--text-1)", fontSize: 13, fontWeight: 600 }}>SMS: transakcje paper tradingu</div>
              <div style={S.desc}>Wysyła SMS po każdej wykonanej wirtualnej transakcji KUP lub SPRZEDAJ. Odrzucone zlecenia są pomijane.</div>
            </div>
            <Toggle value={draft.paper_trading_sms.enabled} onChange={v => setSection("paper_trading_sms", "enabled", v)} />
          </div>

          {/* Portfolio sell urgent */}
          <div style={{ display: "flex", alignItems: "flex-start", gap: 16, padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
            <div style={{ flex: 1 }}>
              <div style={{ color: "var(--text-1)", fontSize: 13, fontWeight: 600 }}>SMS: pilna sprzedaż z portfela</div>
              <div style={S.desc}>Aktywo z portfela z rekomendacją SPRZEDAJ + wysoki risk lub fragility.</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
              <Toggle value={draft.portfolio_sell_urgent.enabled} onChange={v => setSection("portfolio_sell_urgent", "enabled", v)} />
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={S.desc}>Cooldown (min):</span>
                <NumInput
                  value={draft.portfolio_sell_urgent.cooldown_minutes}
                  onChange={v => setSection("portfolio_sell_urgent", "cooldown_minutes", v)}
                  min={60}
                  max={10080}
                  step={60}
                />
              </div>
            </div>
          </div>

          {/* Pre-market gap */}
          <div style={{ display: "flex", alignItems: "flex-start", gap: 16, padding: "10px 0" }}>
            <div style={{ flex: 1 }}>
              <div style={{ color: "var(--text-1)", fontSize: 13, fontWeight: 600 }}>SMS: luka pre-market</div>
              <div style={S.desc}>Alert gdy cena pre-market odbiega od wczorajszego zamknięcia o więcej niż próg. Okno: 10:00–15:25 PL (co 15 min).</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
              <Toggle value={draft.premarket_gap.enabled} onChange={v => setSection("premarket_gap", "enabled", v)} />
              <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={S.desc}>Portfel (%):</span>
                  <NumInput
                    value={draft.premarket_gap.portfolio_threshold_pct}
                    onChange={v => setSection("premarket_gap", "portfolio_threshold_pct", v)}
                    min={0.5}
                    max={20}
                    step={0.5}
                  />
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={S.desc}>Watchlist (%):</span>
                  <NumInput
                    value={draft.premarket_gap.watchlist_threshold_pct}
                    onChange={v => setSection("premarket_gap", "watchlist_threshold_pct", v)}
                    min={0.5}
                    max={20}
                    step={0.5}
                  />
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* Zapisz */}
      {msg && (
        <div style={{
          marginBottom: 12,
          padding: "9px 14px",
          borderRadius: 8,
          fontSize: 13,
          background: msg.type === "ok" ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
          border: `1px solid ${msg.type === "ok" ? "#22c55e" : "#ef4444"}`,
          color: msg.type === "ok" ? "#86efac" : "#fca5a5",
        }}>
          {msg.text}
        </div>
      )}
      <div style={{ display: "flex", gap: 10 }}>
        <button
          onClick={save}
          disabled={saving || !hasChanges}
          style={{
            background: hasChanges ? "#6366f1" : "#334155",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            padding: "9px 22px",
            fontSize: 14,
            fontWeight: 600,
            cursor: hasChanges ? "pointer" : "default",
          }}
        >
          {saving ? "Zapisuję..." : hasChanges ? "Zapisz zmiany" : "Brak zmian"}
        </button>
        <button
          onClick={() => { setDraft(JSON.parse(JSON.stringify(cfg))); setMsg(null); }}
          disabled={!hasChanges}
          style={{
            background: "transparent",
            color: "var(--text-3)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "9px 16px",
            fontSize: 13,
            cursor: hasChanges ? "pointer" : "default",
          }}
        >
          Cofnij zmiany
        </button>
      </div>
    </div>
  );
}
