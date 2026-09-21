import { useEffect, useMemo, useState } from "react";
import { diagnoseText, fetchSampleManifest, validateManifest } from "./api";
import type { ClusterRecord, DiagnoseResponse, ValidationResponse } from "./types";
import { ManifestEditor } from "./components/ManifestEditor";
import { SuggestionCard } from "./components/SuggestionCard";
import { ClusterGrid } from "./components/ClusterGrid";
import { ClusterDetail } from "./components/ClusterDetail";

const SAMPLE_TEXT =
  "Hello 世界！ مرحبًا नमस्ते é 👨‍👩‍👧‍👦 🤷🏽‍♂️ 🇯🇵 …— 𠮷 á ฟ ✓";

export default function App() {
  const [text, setText] = useState(SAMPLE_TEXT);
  const [manifestText, setManifestText] = useState("");
  const [manifestLoaded, setManifestLoaded] = useState(false);
  const [mode, setMode] = useState<"cluster" | "codepoint">("cluster");
  const [validation, setValidation] = useState<ValidationResponse | null>(null);
  const [validating, setValidating] = useState(false);
  const [result, setResult] = useState<DiagnoseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "problem">("all");

  useEffect(() => {
    fetchSampleManifest()
      .then((t) => {
        setManifestText(t);
        setManifestLoaded(true);
      })
      .catch(() => setManifestLoaded(false));
  }, []);

  async function runValidate(): Promise<boolean> {
    setValidating(true);
    try {
      const v = await validateManifest(manifestText);
      setValidation(v);
      return v.valid;
    } catch (e) {
      setValidation({ valid: false, error: { kind: "network", message: String(e) } });
      return false;
    } finally {
      setValidating(false);
    }
  }

  async function runDiagnose() {
    setLoading(true);
    setError(null);
    const ok = await runValidate();
    if (!ok) {
      setLoading(false);
      setResult(null);
      return;
    }
    try {
      const r = await diagnoseText(text, manifestText, mode);
      setResult(r);
      const firstProblem = r.clusters.find((c) => c.status !== "ok");
      setSelected(firstProblem ? firstProblem.index : r.clusters[0]?.index ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  const selectedCluster: ClusterRecord | null = useMemo(() => {
    if (!result || selected === null) return null;
    return result.clusters.find((c) => c.index === selected) ?? null;
  }, [result, selected]);

  const problemClusters = useMemo(
    () => (result ? result.clusters.filter((c) => c.status !== "ok") : []),
    [result],
  );
  const manifestIssues = useMemo(
    () => (result ? result.issues.filter((i) => ["alias_cycle", "dangling_font", "duplicate_priority"].includes(i.kind)) : []),
    [result],
  );

  return (
    <div className="app">
      <header className="topbar">
        <h1>🔤 多语言字体回退诊断台</h1>
        <span className="sub">
          UAX #29 字素簇切分 · 可配置字体优先级 · 缺字 / 组合字符 / 优先级循环定位
        </span>
      </header>

      <main className="layout">
        {/* ---------- left column: inputs ---------- */}
        <div>
          <div className="panel">
            <h2>
              混合语言文本
              <span className="hint">直接粘贴，支持组合记号、ZWJ emoji、旗帜序列、辅助平面汉字</span>
            </h2>
            <textarea
              id="sample-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              spellCheck={false}
            />
            <div className="toolbar" style={{ marginTop: 10 }}>
              <button className="primary" onClick={runDiagnose} disabled={loading || !manifestLoaded}>
                {loading ? "诊断中…" : "▶ 开始诊断"}
              </button>
              <div className="mode-toggle" title="回退解析模式">
                <button className={mode === "cluster" ? "active" : ""} onClick={() => setMode("cluster")}>
                  逐簇整选
                </button>
                <button className={mode === "codepoint" ? "active" : ""} onClick={() => setMode("codepoint")}>
                  逐码位回退
                </button>
              </div>
            </div>
            <div className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>
              逐簇整选：优先选择能覆盖整簇的字体（CSS font-family 语义）；逐码位：每个码位独立
              走优先级（浏览器对缺字簇的实际行为，可暴露组合记号拆分）。
            </div>
            {error && <div className="error-text">{error}</div>}
          </div>

          <ManifestEditor
            value={manifestText}
            onChange={(v) => {
              setManifestText(v);
              setValidation(null);
            }}
            validation={validation}
            validating={validating}
            onValidate={runValidate}
          />
        </div>

        {/* ---------- right column: results ---------- */}
        <div>
          {!result && (
            <div className="panel">
              <div className="empty">
                诊断结果将显示在这里。
                <br />
                点击「▶ 开始诊断」分析文本中每个字素簇的字体回退链。
              </div>
            </div>
          )}

          {result && (
            <>
              <div className="stats">
                <div className="stat">
                  <div className="num">{result.summary.clusterCount}</div>
                  <div className="lbl">字素簇</div>
                </div>
                <div className="stat">
                  <div className="num">{result.summary.codepointCount}</div>
                  <div className="lbl">码位</div>
                </div>
                <div className={`stat ${result.summary.missingCount ? "bad" : ""}`}>
                  <div className="num">{result.summary.missingCount}</div>
                  <div className="lbl">缺字簇</div>
                </div>
                <div className={`stat ${result.summary.splitCount ? "split" : ""}`}>
                  <div className="num">{result.summary.splitCount}</div>
                  <div className="lbl">拆分/组合异常</div>
                </div>
                <div className={`stat ${result.summary.defaultedCount ? "default" : ""}`}>
                  <div className="num">{result.summary.defaultedCount}</div>
                  <div className="lbl">走兜底</div>
                </div>
                <div className="stat">
                  <div className="num">{result.manifest.fontCount}</div>
                  <div className="lbl">清单字体</div>
                </div>
              </div>

              {manifestIssues.length > 0 && (
                <div className="panel">
                  <h2>
                    ⟳ 优先级 / 别名链问题
                    <span className="hint">清单级别的循环与悬空引用，对所有文本生效</span>
                  </h2>
                  {manifestIssues.map((iss, i) => (
                    <div key={i} className={`issue-line ${iss.kind === "alias_cycle" ? "error" : "warning"}`}>
                      <span>{iss.kind === "alias_cycle" ? "⟳" : "!"}</span>
                      <div>
                        <div>{iss.message}</div>
                        {iss.chain && (
                          <div className="mono muted" style={{ fontSize: 11.5 }}>
                            {iss.chain.join(" → ")}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {result.manifest.warnings.length > 0 && (
                <div className="panel">
                  <h2>清单提示</h2>
                  {result.manifest.warnings.map((w, i) => (
                    <div key={i} className="warn-line">
                      ⚠ {w}
                    </div>
                  ))}
                </div>
              )}

              <div className="panel">
                <h2>
                  🛠 可复制的修复建议
                  <span className="hint">
                    {result.suggestions.length} 条 · 片段可直接合并进清单 JSON
                  </span>
                </h2>
                {result.suggestions.length === 0 && <div className="empty">未发现需要修复的问题 🎉</div>}
                {result.suggestions.map((s) => (
                  <SuggestionCard key={s.id} s={s} />
                ))}
              </div>

              <div className="panel">
                <h2>
                  逐簇回退链
                  <span className="hint">点击字素簇查看码位构成与完整回退尝试链</span>
                </h2>
                <div className="toolbar" style={{ marginBottom: 10 }}>
                  <div className="mode-toggle">
                    <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
                      全部 {result.summary.clusterCount}
                    </button>
                    <button className={filter === "problem" ? "active" : ""} onClick={() => setFilter("problem")}>
                      仅问题 {problemClusters.length}
                    </button>
                  </div>
                </div>

                {problemClusters.length > 0 && (
                  <div style={{ marginBottom: 10 }}>
                    {problemClusters.map((c) => (
                      <button
                        key={c.index}
                        className="tiny"
                        style={{ marginRight: 6 }}
                        onClick={() => {
                          setFilter("all");
                          setSelected(c.index);
                        }}
                      >
                        {c.text === " " ? "␠" : c.text} #{c.index}
                      </button>
                    ))}
                  </div>
                )}

                <ClusterGrid
                  clusters={result.clusters}
                  selected={selected}
                  filter={filter}
                  onSelect={setSelected}
                />
                {selectedCluster && <ClusterDetail cluster={selectedCluster} />}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
