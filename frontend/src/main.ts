import "./styles.css";
import { diagnose, fetchDefaults, validateManifest } from "./api";
import type {
  ClusterResult,
  Diagnostic,
  DiagnoseResponse,
  Severity,
} from "./types";

/* --------------- 状态 --------------- */

const state = {
  priority: [] as string[],
  result: null as DiagnoseResponse | null,
  filter: "all" as "all" | "error" | "warning" | "ok",
};

/* --------------- DOM 工具 --------------- */

function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {},
  children: (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "className") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) {
    node.append(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}

function clear(node: HTMLElement): void {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function copyText(text: string, btn: HTMLButtonElement): void {
  const done = () => {
    const old = btn.textContent;
    btn.textContent = "已复制 ✓";
    setTimeout(() => (btn.textContent = old), 1200);
  };
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallback());
  } else {
    fallback();
  }
  function fallback() {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    done();
  }
}

/* --------------- 页面骨架 --------------- */

const app = document.getElementById("app")!;

app.append(
  h("header", { className: "topbar" }, [
    h("h1", {}, ["多语言字体回退诊断台"]),
    h("p", { className: "subtitle" }, [
      "按 Unicode 字素簇切分文本，依据字体优先级解析每个簇的实际字体来源，定位缺字、组合字符与优先级循环。",
    ]),
  ]),
);

const main = h("main", { className: "layout" });
app.append(main);

/* ----- 左栏：输入 ----- */
const left = h("section", { className: "panel inputs" });
main.append(left);

left.append(h("h2", {}, ["① 混合语言文本"]));
const textInput = h("textarea", {
  id: "textInput",
  rows: "5",
  placeholder: "粘贴混合语言文本，例如：Hello 你好世界！ café 👨‍👩‍👧‍👦",
  spellcheck: "false",
});
left.append(textInput);

left.append(h("h2", {}, ["② 字体优先级（高 → 低）"]));
const priorityList = h("ul", { className: "priority-list" });
const priorityInput = h("input", {
  type: "text",
  placeholder: "字体名称，需与清单中的 name 一致",
});
const addPriorityBtn = h("button", { className: "btn small" }, ["添加"]);
addPriorityBtn.type = "button";
left.append(priorityList, h("div", { className: "row" }, [priorityInput, addPriorityBtn]));

left.append(h("h2", {}, ["③ 字体覆盖清单（JSON）"]));
const manifestEditor = h("textarea", {
  id: "manifestEditor",
  rows: "14",
  className: "code",
  spellcheck: "false",
});
const manifestStatus = h("div", { className: "manifest-status" });
const uploadBtn = h("button", { className: "btn small" }, ["上传清单…"]);
uploadBtn.type = "button";
const sampleBtn = h("button", { className: "btn small" }, ["载入示例"]);
sampleBtn.type = "button";
const validateBtn = h("button", { className: "btn small" }, ["校验清单"]);
validateBtn.type = "button";
const fileInput = h("input", { type: "file", accept: ".json,application/json" });
fileInput.style.display = "none";
left.append(
  manifestEditor,
  h("div", { className: "row" }, [uploadBtn, sampleBtn, validateBtn, fileInput]),
  manifestStatus,
);

const diagnoseBtn = h("button", { className: "btn primary" }, ["开始诊断"]);
diagnoseBtn.type = "button";
left.append(diagnoseBtn);

/* ----- 右栏：结果 ----- */
const right = h("section", { className: "panel results" });
main.append(right);
const summaryBar = h("div", { className: "summary-bar" });
const globalDiagsBox = h("div", { className: "global-diags" });
const filterBar = h("div", { className: "filter-bar" });
const clusterList = h("div", { className: "cluster-list" });
const placeholder = h("p", { className: "placeholder" }, [
  "在左侧输入文本与覆盖清单，点击「开始诊断」。",
]);
right.append(summaryBar, globalDiagsBox, filterBar, clusterList, placeholder);

/* --------------- 优先级编辑器 --------------- */

function renderPriority(): void {
  clear(priorityList);
  state.priority.forEach((name, i) => {
    const mkBtn = (label: string, title: string, fn: () => void) => {
      const b = h("button", { className: "icon-btn", title }, [label]);
      b.type = "button";
      b.onclick = fn;
      return b;
    };
    priorityList.append(
      h("li", {}, [
        h("span", { className: "prio-name" }, [name]),
        mkBtn("↑", "上移", () => move(i, -1)),
        mkBtn("↓", "下移", () => move(i, 1)),
        mkBtn("✕", "移除", () => {
          state.priority.splice(i, 1);
          renderPriority();
        }),
      ]),
    );
  });
}

function move(i: number, delta: number): void {
  const j = i + delta;
  if (j < 0 || j >= state.priority.length) return;
  [state.priority[i], state.priority[j]] = [state.priority[j], state.priority[i]];
  renderPriority();
}

addPriorityBtn.onclick = () => {
  const name = priorityInput.value.trim();
  if (!name) return;
  state.priority.push(name);
  priorityInput.value = "";
  renderPriority();
};
priorityInput.onkeydown = (e) => {
  if (e.key === "Enter") addPriorityBtn.click();
};

/* --------------- 清单编辑器 --------------- */

function parseManifestFromEditor(): unknown | null {
  try {
    return JSON.parse(manifestEditor.value);
  } catch (err) {
    showManifestStatus(`JSON 解析失败：${(err as Error).message}`, false);
    return null;
  }
}

function showManifestStatus(msg: string, ok: boolean): void {
  clear(manifestStatus);
  manifestStatus.append(
    h("span", { className: ok ? "status-ok" : "status-err" }, [msg]),
  );
}

sampleBtn.onclick = () => loadDefaults();
uploadBtn.onclick = () => fileInput.click();
fileInput.onchange = async () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  const text = await file.text();
  manifestEditor.value = text;
  fileInput.value = "";
  try {
    const parsed = JSON.parse(text) as { priority?: string[] };
    if (Array.isArray(parsed.priority) && parsed.priority.length) {
      state.priority = parsed.priority.map(String);
      renderPriority();
    }
    showManifestStatus(`已载入 “${file.name}”`, true);
  } catch {
    showManifestStatus("文件不是合法 JSON，请修正后再诊断。", false);
  }
};

validateBtn.onclick = async () => {
  const manifest = parseManifestFromEditor();
  if (manifest === null) return;
  try {
    const res = await validateManifest(manifest);
    if (res.ok) {
      showManifestStatus(
        `清单有效：${res.fontCount} 款字体，共 ${res.codepointCount.toLocaleString()} 个码点。`,
        true,
      );
    } else {
      showManifestStatus(`发现 ${res.errors.length} 处问题：${res.errors[0]}`, false);
    }
  } catch (err) {
    showManifestStatus((err as Error).message, false);
  }
};

/* --------------- 诊断渲染 --------------- */

const SEVERITY_LABEL: Record<Severity, string> = {
  error: "错误",
  warning: "警告",
  info: "提示",
};

function diagCard(d: Diagnostic): HTMLElement {
  const card = h("div", { className: `diag sev-${d.severity}` }, [
    h("div", { className: "diag-head" }, [
      h("span", { className: `badge sev-${d.severity}` }, [
        SEVERITY_LABEL[d.severity],
      ]),
      h("code", { className: "diag-code" }, [d.code]),
    ]),
    h("p", { className: "diag-msg" }, [d.message]),
  ]);
  if (d.fix) {
    const copyBtn = h("button", { className: "btn tiny" }, ["复制修复建议"]);
    copyBtn.type = "button";
    copyBtn.onclick = () => copyText(d.fix!, copyBtn);
    card.append(h("pre", { className: "fix" }, [d.fix]), copyBtn);
  }
  return card;
}

function clusterSeverity(c: ClusterResult): Severity {
  if (c.status === "missing" || c.diagnostics.some((d) => d.severity === "error"))
    return "error";
  if (c.status === "partial" || c.diagnostics.some((d) => d.severity === "warning"))
    return "warning";
  return "info";
}

function clusterCard(c: ClusterResult): HTMLElement {
  const sev = clusterSeverity(c);
  const statusLabel =
    c.status === "ok" ? "已解析" : c.status === "partial" ? "部分覆盖" : "缺字";

  const chain = h("div", { className: "chain" });
  c.chain.forEach((entry, i) => {
    if (i > 0) chain.append(h("span", { className: "chain-arrow" }, ["→"]));
    chain.append(
      h(
        "span",
        {
          className: `chain-chip ${entry.verdict}`,
          title:
            entry.verdict === "hit"
              ? "完整覆盖该簇"
              : `缺少：${entry.missing.join(" ")}`,
        },
        [`${entry.font} ${entry.verdict === "hit" ? "✓" : "✗"}`],
      ),
    );
  });

  const fontLine =
    c.status === "ok"
      ? `字体来源：${c.resolvedFont}`
      : c.bestPartialFont
        ? `无完整命中，最佳部分匹配：${c.bestPartialFont}`
        : "字体来源：无（所有字体均未命中）";

  const card = h("div", { className: `cluster-card sev-${sev}` }, [
    h("div", { className: "cluster-top" }, [
      h("span", { className: "glyph" }, [c.text]),
      h("div", { className: "cluster-meta" }, [
        h("div", {}, [
          h("span", { className: `badge status-${c.status}` }, [statusLabel]),
          h("span", { className: "mono dim" }, [
            ` #${c.index} · 偏移 ${c.start}–${c.end}`,
          ]),
        ]),
        h("div", { className: "mono" }, [c.codepoints.join(" ")]),
        h("div", { className: "dim names" }, [c.names.join(" · ")]),
        h("div", { className: "font-line" }, [fontLine]),
      ]),
    ]),
    chain,
  ]);
  for (const d of c.diagnostics) card.append(diagCard(d));
  return card;
}

function renderResults(res: DiagnoseResponse): void {
  placeholder.remove();
  clear(summaryBar);
  clear(globalDiagsBox);
  clear(filterBar);
  clear(clusterList);

  const s = res.summary;
  summaryBar.append(
    h("span", { className: "stat" }, [`共 ${s.total} 簇`]),
    h("span", { className: "stat ok" }, [`✓ ${s.ok}`]),
    h("span", { className: "stat partial" }, [`◐ ${s.partial}`]),
    h("span", { className: "stat missing" }, [`✗ ${s.missing}`]),
    h("span", { className: "stat err" }, [`错误 ${s.errors}`]),
    h("span", { className: "stat warn" }, [`警告 ${s.warnings}`]),
    h("span", { className: "stat dim" }, [
      `解析顺序：${res.effectiveOrder.join(" → ") || "（空）"}`,
    ]),
  );

  for (const d of res.globalDiagnostics) globalDiagsBox.append(diagCard(d));

  const filters: [typeof state.filter, string][] = [
    ["all", "全部"],
    ["error", "问题"],
    ["warning", "警告"],
    ["ok", "正常"],
  ];
  for (const [key, label] of filters) {
    const b = h(
      "button",
      { className: `btn tiny ${state.filter === key ? "active" : ""}` },
      [label],
    );
    b.type = "button";
    b.onclick = () => {
      state.filter = key;
      renderResults(res);
    };
    filterBar.append(b);
  }

  const shown = res.clusters.filter((c) => {
    const sev = clusterSeverity(c);
    if (state.filter === "error") return sev === "error";
    if (state.filter === "warning") return sev === "warning";
    if (state.filter === "ok") return c.status === "ok";
    return true;
  });
  if (!shown.length) {
    clusterList.append(h("p", { className: "placeholder" }, ["该筛选条件下没有字素簇。"]));
  }
  for (const c of shown) clusterList.append(clusterCard(c));
}

/* --------------- 事件 --------------- */

diagnoseBtn.onclick = async () => {
  const manifest = parseManifestFromEditor();
  if (manifest === null) return;
  diagnoseBtn.disabled = true;
  diagnoseBtn.textContent = "诊断中…";
  try {
    const res = await diagnose(textInput.value, manifest, state.priority);
    state.result = res;
    state.filter = "all";
    renderResults(res);
  } catch (err) {
    showManifestStatus((err as Error).message, false);
  } finally {
    diagnoseBtn.disabled = false;
    diagnoseBtn.textContent = "开始诊断";
  }
};

async function loadDefaults(): Promise<void> {
  const d = await fetchDefaults();
  textInput.value = d.sampleText;
  manifestEditor.value = JSON.stringify(d.manifest, null, 2);
  state.priority = [...d.priority];
  renderPriority();
  showManifestStatus("已载入示例清单。", true);
}

loadDefaults().catch(() => showManifestStatus("无法连接后端 /api/defaults。", false));
