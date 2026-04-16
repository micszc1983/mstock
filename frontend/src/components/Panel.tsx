import type { ReactNode } from "react";
export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <div className="panel"><div className="panel-title">{title}</div>{children}</div>;
}
export function MetaRow({ label, value }: { label: string; value: string }) {
  return <div className="meta-row"><span>{label}</span><strong>{value}</strong></div>;
}
export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "bad" }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}
