import type { ClusterRecord } from "../types";

const STATUS_GLYPH: Record<string, string> = {
  ok: "ok",
  missing: "missing",
  split: "split",
  default: "default",
};

export function ClusterGrid({
  clusters,
  selected,
  filter,
  onSelect,
}: {
  clusters: ClusterRecord[];
  selected: number | null;
  filter: "all" | "problem";
  onSelect: (i: number) => void;
}) {
  const shown = filter === "problem" ? clusters.filter((c) => c.status !== "ok") : clusters;
  if (shown.length === 0) {
    return <div className="empty">{filter === "problem" ? "🎉 没有发现问题字素簇" : "粘贴文本并运行诊断"}</div>;
  }
  return (
    <div className="cluster-grid">
      {shown.map((c) => (
        <button
          key={c.index}
          className={`glyph-chip ${STATUS_GLYPH[c.status] ?? "ok"} ${
            selected === c.index ? "selected" : ""
          }`}
          onClick={() => onSelect(c.index)}
          title={`#${c.index} ${c.kind} → ${c.chosenFont ?? "无字体"}`}
        >
          <span className="ch">{c.text}</span>
          <span className="idx">#{c.index}</span>
        </button>
      ))}
    </div>
  );
}
