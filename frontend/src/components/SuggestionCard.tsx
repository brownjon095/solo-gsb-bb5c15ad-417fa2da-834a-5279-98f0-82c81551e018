import { useState } from "react";
import type { Suggestion } from "../types";

export function SuggestionCard({ s }: { s: Suggestion }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!s.snippet) return;
    try {
      await navigator.clipboard.writeText(s.snippet);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = s.snippet;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className={`suggestion ${s.severity}`}>
      <div className="head">
        {s.severity === "error" ? "❌" : "⚠️"} {s.title}
      </div>
      <div className="body">
        <div>{s.problem}</div>
        <div style={{ marginTop: 6 }}>{s.fix}</div>
        {s.snippet && (
          <>
            <pre>{s.snippet}</pre>
            <button className={`tiny ${copied ? "copied" : ""}`} onClick={copy}>
              {copied ? "✓ 已复制" : "复制修复片段"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
