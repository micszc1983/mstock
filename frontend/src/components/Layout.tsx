import type { ReactNode } from "react";
export function PageContainer({ children }: { children: ReactNode }) {
  return <div className="app-shell"><div className="container">{children}</div></div>;
}
export function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return <section className="section"><div className="section-header"><h2>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</div>{children}</section>;
}
