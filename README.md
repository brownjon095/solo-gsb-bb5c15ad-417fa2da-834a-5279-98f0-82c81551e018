# 多语言字体回退诊断台 (Font Fallback Workbench)

粘贴一段混合语言文本、上传一份「字体覆盖清单」，系统会：

1. 按 **UAX #29 扩展字素簇**（grapheme cluster）切分文本——组合字符、emoji ZWJ 连字、
   旗帜序列、肤色修饰都作为一个整体处理；
2. 按你配置的 **字体优先级（fallback_order）+ 别名链（alias_for）** 逐簇解析
   **实际生效的字体来源**；
3. 对三类问题给出**带文本位置的定位解释**：
   - **缺字**（tofu）——码位在所有字体（含兜底）中均无覆盖；
   - **组合字符分离**——高优先字体含基字但不含组合记号 / 变体选择符，逐码位回退时会
     与基字错配或显示为豆腐块；ZWJ 连字被拆开时退化为多个独立符号；
   - **优先级循环**——`alias_for` 别名图中的闭环、悬空引用、重复优先级项；
4. 展示**逐簇（或逐码位）的完整回退链**：每款字体命中/缺失了簇中的第几个码位；
5. 生成**可一键复制的修复片段**（按 Unicode 区块聚合的 `blocks` / `codepoints` JSON）。

技术栈：Python 3.12 + FastAPI + [`regex`](https://pypi.org/project/regex/)（后端）、
React 18 + TypeScript + Vite（前端），单容器交付，浏览器直接访问。

> 说明：本工具根据**声明式覆盖清单**模拟字体回退逻辑（等价于浏览器 / HarfBuzz 依据
> cmap 做的字体选择），不实际渲染字形。因此你可以用它在没有安装字体的环境里排查
> `font-family` 栈与字体分包问题。

---

## 一键启动（Docker）

前置条件：已安装 Docker 与 Docker Compose（v2）。

```bash
docker compose up --build
```

启动后打开浏览器访问： **http://localhost:8000**

停止：

```bash
docker compose down
```

端口冲突时改 `docker-compose.yml` 里的 `"8000:8000"`（左侧为宿主机端口）。

---

## 本地开发

### 后端（FastAPI，:8000）

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端（Vite dev server，:5173，代理 /api → :8000）

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 ，修改前端代码热更新；后端修改自动重载。

---

## 覆盖清单格式（JSON）

完整示例见 [`data/sample-coverage.json`](data/sample-coverage.json)（内置在镜像中，
页面首次加载会自动读取它）：

```json
{
  "fallback_order": ["Noto Sans", "Noto Sans CJK SC", "Noto Sans Arabic"],
  "default": "LastResort",
  "fonts": {
    "Noto Sans": {
      "blocks": ["Basic Latin", "General Punctuation"],
      "ranges": [["U+0020", "U+007E"], ["U+2000", "U+206F"]],
      "codepoints": ["U+2026", "…"]
    },
    "Noto Sans CJK SC": { "blocks": ["CJK Unified Ideographs", "Hiragana"] },
    "Old Name": { "alias_for": "Noto Sans" }
  }
}
```

| 字段 | 含义 |
| --- | --- |
| `fallback_order` | 字体名数组，**越靠前优先级越高**，等价于 CSS `font-family` 栈 |
| `default` | 兜底字体名；可填 `"LastResort"`（内置虚拟字体，不覆盖任何码位）或 `null` |
| `fonts.<name>.blocks` | Unicode 区块名（与 [Unicode Blocks.txt](https://www.unicode.org/Public/UCD/latest/ucd/Blocks.txt) 同名，大小写不敏感），整区块覆盖 |
| `fonts.<name>.ranges` | `[起, 止]` 区间数组；端点支持 `U+XXXX`、`0xXXXX` 或单个字面字符；也可直接写区块名字符串 |
| `fonts.<name>.codepoints` | 零散码位数组，同样支持 `U+XXXX` 与字面字符 |
| `fonts.<name>.alias_for` | 把该字体名重定向到另一款字体（用于旧名 / 分包别名）。形成闭环即报「优先级循环」 |

页面里可以直接**编辑**这份 JSON（带即时校验、错误行列号），也可以点「上传 .json」
导入本机清单；「复制修复片段」生成的 JSON 可直接合并进对应字体条目。

### 两种诊断模式

- **逐簇整选**（默认，等价 CSS `font-family`）：选第一個**能覆盖整个字素簇全部码位**
  的字体；若没有任何单款字体能整簇覆盖，会同时报告「真正缺字的码位」与
  「跨字体拆分的码位」。
- **逐码位回退**（浏览器对缺字簇的实际行为）：簇内每个码位独立走优先级，
  可以看到 `á`（`a` + 组合重音）或 ZWJ emoji 被拆到几款字体、具体哪一步开始回退。

---

## HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/sample-manifest` | 内置样例清单 |
| `GET` | `/api/blocks` | 支持的全部 Unicode 区块名及码位区间 |
| `POST` | `/api/validate-manifest` | 校验清单 JSON，返回字体数、生效顺序、循环/悬空/重复问题 |
| `POST` | `/api/diagnose` | 入参 `{ text, manifestText, mode }`，返回逐簇回退链、问题、修复建议 |

诊断响应核心结构：

```jsonc
{
  "summary": { "clusterCount": 33, "missingCount": 3, "splitCount": 0, "...": "..." },
  "issues":   [ { "kind": "alias_cycle", "chain": ["..."], "message": "..." } ],
  "suggestions": [ { "title": "...", "snippet": "可复制 JSON", "copyable": true } ],
  "clusters": [{
    "index": 30, "text": "á", "kind": "combining-sequence",
    "chosenFont": "Noto Sans", "status": "split",
    "codepoints": [ { "cp": "U+0061", "role": "base" }, { "cp": "U+0301", "role": "combining-mark" } ],
    "fallbackChain": [ { "font": "Noto Sans", "covered": [0], "missing": [1] } ]
  }]
}
```

也可直接访问交互式 API 文档：启动后打开 http://localhost:8000/docs 。

---

## 目录结构

```
.
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 路由 / 静态文件托管
│   │   ├── unicode_blocks.py  # Unicode 15.1 区块表
│   │   ├── manifest.py        # 清单解析、区间合并、别名图与循环检测
│   │   ├── segmentation.py    # UAX #29 字素簇切分与码位标注
│   │   └── resolver.py        # 回退解析、问题定位、修复建议生成
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api.ts / types.ts
│   │   └── components/        # 清单编辑、字素簇网格、簇详情、建议卡片
│   ├── package.json / vite.config.ts / tsconfig.json
│   └── index.html
├── data/sample-coverage.json  # 内置示例清单（含别名环演示）
├── Dockerfile                 # 多阶段：node 构建 → python 运行
└── docker-compose.yml
```

## 诊断结果怎么读

- 字素簇色块底边颜色：🢐 绿=正常命中；红=缺字；紫=跨字体拆分/组合异常；青=走兜底。
- 回退链每一步标注 `覆盖第 n 码位` / `缺第 n 码位`，**第一条绿色「整簇命中」**即
  该簇的实际字体来源；虚线卡片是 `default` 兜底字体；`via X` 表示经由别名链到达。
- 码位表给出 Unicode 名称、区块、通用类别（Mn=非延伸记号等）与规范组合类（ccc），
  便于判断组合字符为什么叠加失败。
