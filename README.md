# 多语言字体回退诊断台（Font Fallback Lab）

粘贴混合语言文本、上传字体覆盖清单，系统按 **Unicode 字素簇（grapheme cluster）** 切分文本，
依据**可配置的字体优先级**解析每个字素簇的实际字体来源，并对**缺字、组合字符、优先级循环**
给出定位解释与可复制的修复建议。

- 后端：Python 3.12 · FastAPI（字素簇切分 / 回退解析 / 诊断规则为零依赖纯 Python 核心）
- 前端：TypeScript · Vite（清单编辑、优先级编辑、逐簇回退链预览）
- 交付：多阶段 `Dockerfile` + `docker-compose.yml`，一键启动后浏览器访问

## 快速开始

```bash
docker compose up --build
# 打开 http://localhost:8000
```

不使用 Compose 也可以：

```bash
docker build -t font-fallback-lab .
docker run --rm -p 8000:8000 font-fallback-lab
```

## 使用流程

1. **① 混合语言文本**：粘贴待诊断文本（首次打开已载入示例）。
2. **② 字体优先级**：按从高到低排列候选字体，可增删、上下移动。
3. **③ 字体覆盖清单（JSON）**：直接编辑、上传 `.json` 文件或载入示例；「校验清单」即时反馈格式错误。
4. 点击 **开始诊断**：右栏展示汇总、全局诊断（优先级循环等）与逐簇卡片——
   每个卡片包含簇字形、码点与字符名、实际字体来源、**逐簇回退链**（命中 ✓ / 未命中 ✗）
   以及**可一键复制的修复建议**。

## 覆盖清单格式

```jsonc
{
  "fonts": [
    {
      "name": "Acme Sans",                 // 字体名（优先级列表引用此名）
      "coverage": ["U+0020-U+007E", "U+0300-U+036F"],  // 覆盖范围：区间或单码点
      "fallbackTo": "Acme CJK"             // 可选：未命中时跳转的下一字体
    },
    { "name": "Acme CJK",  "coverage": ["U+4E00-U+9FFF"] },
    { "name": "Acme Emoji", "coverage": ["U+1F300-U+1FAFF", "U+200D", "U+FE0F"] }
  ],
  "priority": ["Acme Sans", "Acme CJK", "Acme Emoji"]   // 可选：导入时填入优先级编辑器
}
```

**解析顺序**：依次遍历优先级列表；每访问一个字体后沿其 `fallbackTo` 链继续深入，
全部条目遍历完去重即得最终匹配顺序。字素簇由**第一款覆盖其全部码点**的字体渲染；
组合簇（如 `e + U+0301`、emoji ZWJ 序列）要求同一字体覆盖簇内所有码点，否则判定拆分渲染。

## 诊断码

| 代码 | 级别 | 含义 |
| --- | --- | --- |
| `MISSING_GLYPH` | 错误 | 码点不在任何字体覆盖范围内，附所属 Unicode 区块与补字建议 |
| `PARTIAL_COVERAGE` | 警告 | 无单一字体覆盖整个簇，将被多字体拆分渲染 |
| `COMBINING_CLUSTER` | 提示 | 组合字符簇（附加符号 / emoji ZWJ / 旗帜 / TAG）整体由一款字体渲染 |
| `COMBINING_SPLIT` | 警告 | 组合簇无法由单一字体渲染，基字与附加符号可能错位 |
| `PRIORITY_CYCLE` | 错误 | `fallbackTo` 构成循环（如 A→B→A），附断边建议 |
| `UNKNOWN_FONT` | 警告 | 优先级或 `fallbackTo` 引用了清单中未定义的字体 |
| `DUPLICATE_FONT` | 提示 | 优先级列表中存在重复字体 |
| `UNUSED_FONT` | 提示 | 清单中定义了字体但不在任何解析路径上 |
| `EMPTY_STACK` / `MANIFEST_ERROR` | 错误 | 优先级为空 / 清单格式错误 |

## HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/defaults` | 示例文本与示例清单 |
| POST | `/api/diagnose` | 诊断，请求体 `{text, manifest, priority?}` |
| POST | `/api/manifest/validate` | 校验清单，返回错误列表与统计 |

`/api/diagnose` 响应包含 `clusters`（逐簇结果与回退链）、`globalDiagnostics`、
`summary`、`effectiveOrder`。

## 本地开发

```bash
# 后端（Python 3.12+）
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000

# 前端（Node 20+，另开终端；/api 已代理到 8000）
cd frontend
npm install
npm run dev                            # http://localhost:5173
```

## 测试

核心逻辑（切分 / 解析 / 诊断）仅依赖标准库，可直接运行：

```bash
python3 -m unittest discover -s backend/tests -v
```

## 实现说明

- **字素簇切分**：运行时优先使用 `regex` 库的 `\X`（完整 UAX #29）；未安装时回退到
  内置纯 Python 实现（`backend/app/gcb.py`），覆盖 GB1–GB13 核心规则，包括组合附加符号、
  emoji 修饰符、ZWJ 序列、区域指示符成对、谚文组合与印度系文字 virama 连字（GB9c 近似）。
- **组合簇判定**：一个簇只有被同一字体覆盖全部码点才算 `ok`，否则给出
  `PARTIAL_COVERAGE` / `COMBINING_SPLIT`，避免基字与附加符号来自不同字体导致的错位。
- **循环检测**：对 `fallbackTo` 图做遍历，命中回边即报告完整循环路径，
  解析时在回边处截断，保证诊断自身不会死循环。
