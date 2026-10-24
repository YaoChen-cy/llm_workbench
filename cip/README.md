# CIP Monthly Provision Summarizer

把当月的 CIP "Monthly Change in Provision" PDF 放进文件夹，运行一条命令，每家公司会得到：

| 输出文件 | 内容 |
|---|---|
| `<公司>_summary.docx` | 正文分 **Situation Recap** 和 **Recent Development** 两部分，每部分 2–4 点，关键信息加粗；每点后面标引用 `[PR-1, PR-2]`；文末附来源表（ID → 章节 › 小标题, 页码 → 原文） |
| `<公司>_cited.pdf` | 原 PDF 的副本：被引用的段落标黄，页边写上对应的 ID |
| `review_checklist.xlsx` | 当月所有公司共用一个文件。每点一行，含两项校验结果；没通过校验的行标红，留有审核签字列 |

> 仓库中的 PDF 和示例均为**虚构案例**（Harborline / Velora），只用来测试流程。

---

## 0. 安装与运行

> 以下命令都在 `cip/` 目录下执行（`cd cip`）。依赖统一在仓库根目录的 `requirements.txt`。

```bash
pip install -r ../requirements.txt
```

**接入内部 LLM**：只需要改 `llm_client.py` 里的 `_call_api()`。默认按 OpenAI 兼容接口写好了，如果你们的网关也是这种格式，设置环境变量即可：

```bash
export LLM_BASE_URL="https://内部网关/v1"
export LLM_API_KEY="..."
export LLM_MODEL="模型名"
```

**运行**：

```bash
python run.py --month 2026-10          # 处理 input/2026-10/ 下所有 PDF
python run.py --pdf some/memo.pdf      # 处理单个 PDF
LLM_MODE=mock python run.py --month 2026-10   # 不调用 API，用预置的假回复跑通全流程
```

**单个 PDF 的处理流程**（每家公司调用 2 次 LLM）：

```
parse.py      从 "Company Overview" 开始，到 Sign-off 结束；跳过表格、页眉页脚
              → 切成段落，每段编 ID：OV/RR/TU/PR/OL-序号，并记录所属小标题和页码
summarize.py  LLM 调用 1：system prompt + 风格指南 + few-shot 示例 + 正文 → JSON（每点带引用）
              JSON 格式不对或引用了不存在的 ID 时，自动让模型重写一次
verify.py     ① 程序校验：每点中的数字必须出现在它引用的段落里（$1.4bn 与 $1.42bn 这类四舍五入视为一致）
              ② LLM 调用 2：逐点判断引用段落是否支持这句话
export.py     生成 Word / 高亮 PDF / Excel
```

**拿到真实 PDF 后先检查解析结果**：

```bash
python run.py --dump-source 某份真实memo.pdf
```

确认五个大章节都识别到了，段落切分也合理。如果不对，修改 `config.py` 里的 `SECTIONS`（标题的正则）和 `END_PATTERNS`（结束标记）。输出末尾如果出现 `missing sections`，说明某个章节标题没有匹配上。

---

## 把 prompt 调到你们的写作风格（在内部环境执行）

核心思路：**风格写进风格指南，示例负责示范，评估集负责打分**。每次只改一处，跑一次评估，看分数是升还是降。

### 第 1 步：准备数据（约半天，一次性）

挑 15–25 份历史 memo 和对应的人工总结，尽量覆盖不同情况（刚降级的、正在 Chapter 11 的、已经 emerge 的、不同行业）。分成两组：

| 用途 | 数量 | 放在哪里 |
|---|---|---|
| **Few-shot 示例** | 2–3 份，挑写得最好、类型差异最大的 | `prompts/examples/<case>/source.txt` + `summary.md` |
| **评估集** | 其余全部 | `eval/<case>/memo.pdf` + `human_summary.md` |

- 示例的 `source.txt` 用 `python run.py --dump-source xxx.pdf > prompts/examples/<case>/source.txt` 生成。
- `summary.md` / `human_summary.md` 直接粘贴人工总结原文，用 `**...**` 标出原文中加粗的部分。**不需要加引用**。
- 示例和评估集的 case 名不能重复，`eval.py` 会自动跳过重名的 case，避免拿示例来测试。

### 第 2 步：让 LLM 归纳风格指南

```bash
python derive_style.py
```

LLM 会读入所有人工总结，生成 `prompts/style_guide.draft.md`，内容包括：点数、每点写什么、开头怎么写、数字格式、缩写习惯、加粗规则、篇幅和忌讳。

**这一步一定要人工过一遍**：删掉不对的规则，补上团队的隐性规矩（比如“永远写 coverage %”、“法院名称不写”），然后把它替换为 `prompts/style_guide.md`。风格指南控制在 1 页以内，规则越具体越好。

> 没有脚本的话也可以手动做：把 `prompts/meta/derive_style_guide.md` 里的 `{summaries}` 替换成 10 篇以上人工总结，粘贴到内部 LLM 的对话界面里执行。

### 第 3 步：跑基线评估

```bash
python eval.py --note "baseline"
```

对评估集中的每份 memo，脚本会先生成 AI 总结，再让 LLM 当评委，对照人工总结打 1–5 分：

- **coverage**：人工总结写到的关键事实，AI 是否都覆盖了
- **accuracy**：事实和数字是否正确（出现会误导委员会的错误时，最高 2 分）
- **style**：结构、详略、用词、加粗是否接近人工总结

结果写入 `eval/reports/<时间>.xlsx`，里面逐份列出 **missing_key_points / errors / style_gaps**，并把 AI 总结和人工总结并排放着；历史分数累积在 `eval/reports/history.csv`。

### 第 4 步：迭代（一般 3–5 轮就稳定）

每轮读一遍报告里的 `style_gaps` 和 `missing_key_points`，找出**反复出现**的问题，再按下表修改：

| 现象 | 改哪里 |
|---|---|
| 遗漏某类关键信息（比如总是漏写 recovery %） | `style_guide.md` 的 *Content selection* 里加一条“必须包含……” |
| 用词或格式不对（比如写 "$45 million"，团队习惯写 "$45.0mm"） | `style_guide.md` 的 *Phrasing*，最好附上正确写法的原句 |
| 加粗太多或太少 | `style_guide.md` 的 *Bolding* |
| 点数或篇幅不对 | `config.POINTS_PER_SECTION` 和风格指南的 *Length* |
| 整体“味道”不对 | 换 few-shot 示例，选最典型的；示例的作用大于规则 |
| 出现编造或算错的数字 | `system.md` 的 *Rules — accuracy*（一般不需要改，靠校验来兜底） |

每改一处就跑一次 `python eval.py --note "加了 recovery% 规则"`，在 `history.csv` 中比较分数。**分数没有提升就回滚**。

**几个经验：**
- 温度保持 0（`config.LLM_TEMPERATURE`），这样同一个 prompt 每次的结果可比。
- 规则描述“要做什么”，不要只写“不要做什么”；附一句原文例句的效果最好。
- 示例 2–3 份就够了，再多收益很小，还可能让模型照抄示例的句子。
- LLM 评委的分数只是参考，**每轮至少亲自读 3 份**，确认分数和你自己的判断一致。
- 目标：accuracy 稳定在 5，coverage 和 style 在 4 以上，就可以上线试运行。

---

## 上线后的每月流程

1. 把 PDF 放进 `input/YYYY-MM/`
2. 运行 `python run.py --month YYYY-MM`（5–10 家公司并行，约 1–2 分钟）
3. 打开 `review_checklist.xlsx`，**优先看标红的行**，对照 `_cited.pdf` 中的高亮段落核对
4. 在 Word 中修改定稿；标黄的点是没通过校验的，改完后去掉高亮

## 文件结构

```
config.py            所有可调参数（章节标题正则、模型、并发数、点数……）
llm_client.py        LLM 调用（唯一需要接内部 API 的地方）
parse.py             PDF 解析与切段编号
summarize.py         拼装 prompt 并生成总结
verify.py            数字校验 + LLM 校验
export.py            Word / Excel / 高亮 PDF
run.py               每月运行入口
derive_style.py      从人工总结归纳风格指南
eval.py              对照人工总结打分
prompts/system.md          任务、准确性规则、输出格式
prompts/style_guide.md     团队风格指南（第 2 步生成后替换）
prompts/verify.md          校验 prompt
prompts/examples/          few-shot 示例
prompts/meta/              风格归纳与评估打分用的 prompt
tests/fixtures/            mock 模式使用的假回复
tools/make_sample_pdf.py   生成虚构测试 PDF
```
