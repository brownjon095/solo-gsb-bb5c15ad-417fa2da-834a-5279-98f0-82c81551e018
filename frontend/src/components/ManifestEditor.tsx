import { useRef } from "react";
import type { ValidationResponse } from "../types";

interface Props {
  value: string;
  onChange: (v: string) => void;
  validation: ValidationResponse | null;
  validating: boolean;
  onValidate: () => void;
}

export function ManifestEditor({ value, onChange, validation, validating, onValidate }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);

  function handleUpload(file: File | undefined) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => onChange(String(reader.result ?? ""));
    reader.readAsText(file, "utf-8");
  }

  return (
    <div className="panel">
      <h2>
        字体覆盖清单
        <span className="hint">JSON：fallback_order + 每款字体的 blocks/ranges/codepoints</span>
      </h2>
      <textarea
        id="manifest-editor"
        spellCheck={false}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="btn-row">
        <button onClick={onValidate} disabled={validating}>
          {validating ? "校验中…" : "校验清单"}
        </button>
        <button onClick={() => fileRef.current?.click()}>上传 .json</button>
        <input
          ref={fileRef}
          type="file"
          accept=".json,application/json"
          style={{ display: "none" }}
          onChange={(e) => {
            handleUpload(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>

      {!validation && (
        <div className="validation idle">编辑或上传清单后点击「校验清单」；诊断前也会自动校验。</div>
      )}
      {validation?.valid && (
        <div className="validation ok">
          ✓ 清单有效：{validation.fontCount} 款字体；实际生效顺序为
          <div style={{ marginTop: 6 }}>
            {(validation.effectiveOrder ?? []).map((f, i) => (
              <span key={f} className="font-pill">
                {i + 1}. {f}
              </span>
            ))}
          </div>
          {(validation.warnings ?? []).map((w, i) => (
            <div key={i} className="warn-line">⚠ {w}</div>
          ))}
          {(validation.issues ?? []).map((iss, i) => (
            <div
              key={i}
              className={`issue-line ${iss.kind === "alias_cycle" ? "error" : "warning"}`}
            >
              <span>{iss.kind === "alias_cycle" ? "⟳" : "!"}</span>
              <span>{iss.message}</span>
            </div>
          ))}
        </div>
      )}
      {validation && !validation.valid && (
        <div className="validation err">
          ✗ {validation.error?.message}
          {validation.error?.line ? (
            <span className="muted">
              {" "}
              （第 {validation.error.line} 行{validation.error.column ? `第 ${validation.error.column} 列` : ""}）
            </span>
          ) : null}
        </div>
      )}
    </div>
  );
}
