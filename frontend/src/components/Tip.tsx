/**
 * Tip — mały dymek informacyjny (CSS-only, zero bibliotek zewnętrznych).
 *
 * Użycie:
 *   <Tip text="Wyjaśnienie" />          — ikona ⓘ z dymkiem po najechaniu
 *   <Tip text="..." side="left" />      — dymek po lewej
 *
 * Działa przez CSS :hover + ::before/::after na [data-tip].
 */
import type { CSSProperties } from "react";

type TipSide = "top" | "bottom" | "left" | "right";

type Props = {
  text: string;
  side?: TipSide;
  style?: CSSProperties;
  inline?: boolean; // wyświetl inline-block zamiast block
};

export function Tip({ text, side = "top", style, inline }: Props) {
  return (
    <span
      data-tip={text}
      data-tip-side={side}
      aria-label={text}
      style={{
        display: inline ? "inline-block" : "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 14,
        height: 14,
        borderRadius: "50%",
        fontSize: "0.62rem",
        fontWeight: 700,
        cursor: "help",
        flexShrink: 0,
        background: "rgba(128,128,128,.15)",
        color: "var(--text-3)",
        userSelect: "none",
        position: "relative",
        marginLeft: 4,
        ...style,
      }}
    >
      ⓘ
    </span>
  );
}

/** Wersja z etykietą tekstową — do nagłówków tabel */
export function ColTip({ label, text, side = "top", style }: { label: string; text: string; side?: TipSide; style?: CSSProperties }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 2, ...style }}>
      {label}
      <Tip text={text} side={side} />
    </span>
  );
}
