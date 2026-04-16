export function DataTable({ columns, rows, maxRows }: { columns: string[]; rows: Record<string, unknown>[]; maxRows?: number }) {
  const style = maxRows ? { maxHeight: `${maxRows * 2.1 + 2.4}rem`, overflowY: "auto" as const } : undefined;
  return <div className="table-wrap" style={style}><table><thead><tr>{columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{rows.map((row, i)=><tr key={i}>{columns.map(c => <td key={c}>{typeof row[c] === "number" ? (row[c] as number).toFixed(4) : String(row[c] ?? "")}</td>)}</tr>)}</tbody></table></div>;
}
