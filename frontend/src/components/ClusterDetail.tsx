import type { ClusterRecord, CodepointInfo } from "../types";

const ROLE_LABEL: Record<string, string> = {
  base: "基字",
  "combining-mark": "组合记号",
  "variation-selector": "变体选择符",
  "join-control": "连接控制符",
  "emoji-modifier": "emoji 肤色修饰",
  "regional-indicator": "区域指示符",
  "combining-enclosing-keycap": "包围组合键帽",
  "sequence-member": "序列成员",
};

const KIND_LABEL: Record<string, string> = {
  single: "单码位",
  "combining-sequence": "组合字符序列",
  "zwj-sequence": "ZWJ 连字序列",
  "emoji-modifier-sequence": "emoji 修饰序列",
  "variation-sequence": "变体序列",
  "flag-or-tag": "旗帜/标签序列",
  cluster: "多码位字素簇",
};

function CpRow({ cp, highlight }: { cp: CodepointInfo; highlight?: boolean }) {
  return (
    <tr style={highlight ? { background: "rgba(239,106,106,0.06)" } : undefined}>
      <td style={{ fontSize: 18, textAlign: "center", width: 38 }}>{cp.char || "�"}</td>
      <td className="mono">{cp.cp}</td>
      <td>{cp.name}</td>
      <td>{cp.block ?? "—"}</td>
      <td className="mono">{cp.category}</td>
      <td className="mono">{cp.ccc}</td>
      <td>
        <span className={`role-badge ${cp.role}`}>{ROLE_LABEL[cp.role] ?? cp.role}</span>
      </td>
    </tr>
  );
}

export function ClusterDetail({ cluster }: { cluster: ClusterRecord }) {
  const cpCount = cluster.codepoints.length;
  const missingSet = new Set(
    cluster.issues.filter((i) => i.kind === "missing_glyph").map((i) => i.cpIndex),
  );

  return (
    <div className="cluster-detail">
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div className="big">{cluster.text}</div>
        <div>
          <div>
            <strong>字素簇 #{cluster.index}</strong>
            <span className="muted"> · {KIND_LABEL[cluster.kind] ?? cluster.kind}</span>
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            文本偏移 [{cluster.start}, {cluster.end}) · {cpCount} 个码位
          </div>
          <div style={{ marginTop: 6 }}>
            实际字体来源：
            {cluster.chosenFont ? (
              <span className="font-pill">{cluster.chosenFont}</span>
            ) : (
              <span style={{ color: "var(--err)" }}>无（缺字 / 被拆分）</span>
            )}
            {cluster.usedDefault && <span className="font-pill">走兜底字体</span>}
          </div>
        </div>
      </div>

      {cluster.issues.length > 0 && (
        <>
          <div className="section-title">定位解释</div>
          {cluster.issues.map((iss, i) => (
            <div
              key={i}
              className={`issue-line ${
                iss.kind === "missing_glyph" || iss.kind === "zwj_sequence_broken"
                  ? "error"
                  : "warning"
              }`}
            >
              <span>
                {iss.kind === "missing_glyph"
                  ? "⊘"
                  : iss.kind === "zwj_sequence_broken"
                    ? "🔗"
                    : "✂"}
              </span>
              <div>
                <div>{iss.message}</div>
                {iss.at && (
                  <div className="muted" style={{ fontSize: 11.5, fontFamily: "var(--mono)" }}>
                    位置：{iss.at}
                  </div>
                )}
              </div>
            </div>
          ))}
        </>
      )}

      <div className="section-title">码位构成（UAX #29 字素簇）</div>
      <table className="cp-table">
        <thead>
          <tr>
            <th></th>
            <th className="mono">码位</th>
            <th>Unicode 名称</th>
            <th>区块</th>
            <th className="mono">类别</th>
            <th className="mono">ccc</th>
            <th>角色</th>
          </tr>
        </thead>
        <tbody>
          {cluster.codepoints.map((cp, i) => (
            <CpRow key={`${cp.cp}-${i}`} cp={cp} highlight={missingSet.has(i)} />
          ))}
        </tbody>
      </table>

      {cluster.perCodepoint ? (
        <>
          <div className="section-title">逐码位回退链（逐码位模式）</div>
          {cluster.perCodepoint.map((p) => {
            const cp = cluster.codepoints[p.index];
            return (
              <div key={p.index} className="chain">
                <div style={{ fontSize: 12.5, marginBottom: 4 }}>
                  <span style={{ fontSize: 16 }}>{cp.char}</span>{" "}
                  <span className="mono muted">{cp.cp}</span>（{ROLE_LABEL[cp.role]}）→{" "}
                  <strong style={{ color: p.chosen ? "var(--ok)" : "var(--err)" }}>
                    {p.chosen ?? "无字体覆盖"}
                  </strong>
                </div>
                {p.chain.map((step, j) => (
                  <div
                    key={j}
                    className={`chain-step ${step.missing.length ? "miss" : "hit"} ${
                      step.default ? "default-step" : ""
                    }`}
                  >
                    <span className="arrow">{"→"}</span>
                    <span className="mono">{step.font}</span>
                    {step.viaAlias && <span className="alias-tag">via {step.viaAlias}</span>}
                    {step.covered.length > 0 && <span className="tag-cover">命中</span>}
                    {step.missing.length > 0 && (
                      <span className="tag-miss">缺此码位</span>
                    )}
                    {step.default && <span className="alias-tag">兜底</span>}
                  </div>
                ))}
              </div>
            );
          })}
        </>
      ) : (
        <>
          <div className="section-title">逐簇回退链（按优先级尝试）</div>
          <div className="chain">
            {cluster.fallbackChain.map((step, i) => {
              const hit = step.missing.length === 0;
              return (
                <div
                  key={i}
                  className={`chain-step ${hit ? "hit" : "miss"} ${
                    step.default ? "default-step" : ""
                  }`}
                >
                  <span className="arrow">{"→"}</span>
                  <span className="mono">{step.font}</span>
                  {step.viaAlias && <span className="alias-tag">via {step.viaAlias}</span>}
                  {hit ? (
                    <span className="tag-cover">整簇命中</span>
                  ) : (
                    <>
                      {step.covered.length > 0 && (
                        <span className="tag-cover">覆盖第 {step.covered.map((n) => n + 1).join(",")} 码位</span>
                      )}
                      <span className="tag-miss">
                        缺第 {step.missing.map((n) => n + 1).join(",")} 码位
                      </span>
                    </>
                  )}
                  {step.default && <span className="alias-tag">兜底</span>}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
