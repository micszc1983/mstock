import type { ReactNode } from "react";
import { Tip } from "./Tip";

type Props = {
  title: string;
  value: string;
  hint?: string;
  icon?: ReactNode;
  tooltip?: string;
};

export function KpiCard({ title, value, hint, icon, tooltip }: Props) {
  return (
    <div className="kpi-card">
      <div className="kpi-top">
        <div className="kpi-title" style={{ display: "flex", alignItems: "center" }}>
          {title}
          {tooltip && <Tip text={tooltip} side="bottom" />}
        </div>
        {icon ? <div className="kpi-icon">{icon}</div> : null}
      </div>
      <div className="kpi-value">{value}</div>
      {hint ? <div className="kpi-hint">{hint}</div> : null}
    </div>
  );
}
