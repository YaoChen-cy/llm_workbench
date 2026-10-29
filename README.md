# LLM Workbench

本地运行的 LLM 交互界面（英文 UI）：可以浏览本地文件夹、给对话 attach 多个文件，回答中的每个事实都带来源引用，鼠标悬停即可看到原文。

## 启动

```bash
python start.py        # Windows 用 py start.py
```

首次运行会在 `.venv` 中建 Python 环境并安装 `requirements.txt`（版本固定在 `constraints.txt`，需要 Python 3.11+，以及 pip 能访问 PyPI 或公司镜像；有代理时设置 `HTTPS_PROXY` 或 `PIP_INDEX_URL`），然后自动打开 http://localhost:8000 。可选参数：`--port 8001`、`--no-browser`、`--reinstall`。

**整个应用都是 Python**：界面用 [NiceGUI](https://github.com/zauberzeug/nicegui) 编写（`backend/ui.py`），它的浏览器端文件由 pip 安装，仓库里没有 JS/CSS/HTML 文件，也不需要 Node.js。

**复制到另一台电脑**：运行 `python make_package.py`，生成 `llm-workbench-<日期>.zip`。压缩包只包含 git 跟踪的 `.py .txt .md .pdf .json .docx .xlsx` 文件（约 150 KB），不含 `.venv`、`data/` 和任何 key。

**接入公司 API**：复制 `env.example.txt` 为 `env.txt`，填入 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`，或在 **Settings → Company API** 中填写（key 存在 `data/settings.json`，不会提交到 git，也不会被打包）。默认配置已包含 `x-goog-api-key` 请求头、关闭 SSL 校验、绕过代理，与 notebook 中的写法一致。点 **Save & test connection** 验证。

**本地 Ollama**：Settings → Local Ollama。使用 Ollama 原生接口，这样可以设置 `num_ctx`（上下文窗口）。

**允许访问的文件夹**：Settings → Folders。文件浏览器只能读取这些文件夹（含子文件夹）。

**选择项目文件夹**：New project → Browse… 的 **Locations** 列出所有盘符（含映射的网络驱动器）、OneDrive/SharePoint 同步文件夹和常用文件夹。没列出的共享文件夹，在 Folder 框里输入路径（如 `\\server\share\team` 或 `S:\Team`）再点 Browse…。

## 功能（M1）

- 多会话聊天，流式输出，可中途 Stop（已生成的部分会保留）
- 两种方式 attach 文件：右侧 **Files** 面板勾选，或 📎 上传；支持 PDF / DOCX / TXT / MD
- 文件 attach 后在这个会话中持续有效，编号 D1、D2…（移除文件后编号不会重排）
- 回答中的引用 `[D1-p2-13]` 显示为 `D1 · p.2` 标签，悬停可看文件名、页码和原文，点击打开来源；模型编造的 ID 显示为红色 `D1 · ?`
- 文档超出上下文预算时，自动保留和问题最相关的段落，回答下方会注明“documents trimmed”

## 知识库：从样本学习 summary 格式

项目页的 **Knowledge base** 卡片：

1. **Add example…**：上传源文档（PDF/Word/TXT/MD，可多个）和对应的**期望 summary**（Word/PDF/TXT/MD，或直接粘贴）。Word 的标题、项目符号和粗体会保留。
2. **Analysis**（样本行上的 📈 图标）：app 用代码把 summary 的每一句对齐到原文出处（章节、页码，点击可在 PDF 中高亮），并测量原文完整度（哪些章节被用/跳过）、长度与压缩比、原句比例（rephrase）、数字是否出自原文、粗体。
3. **Learn from examples**，分三步：
   - **测量（代码）**：上面的对齐与指标，每个样本算一次并缓存；
   - **分析（LLM）**：模型看的是已对齐的"原文段落 → summary 句子"，总结取舍理由、改写方式、语气；每个样本分析一次并缓存，以后新增样本只分析新的；
   - **合并**：代码汇总测量结果（带支持度，如 3/4 个样本），模型写定性规则，每条规则标注 (k/N)。
4. **审阅并确认**：profile 分三部分——**Measured**（代码测量，只读）、**Learned rules**（可改）、**Pinned rules**（你自己的规则，始终生效、优先级最高，重新学习时不会被覆盖）。每次确认生成新版本，并记录改了什么。

对话中，确认后的 profile + 2–4 组"原文 → summary"改写示例会加进这个项目每个对话的 system prompt（样本里的引用、[1] 编号和 Sources 列表会先去掉，不影响引用格式）。起草的 summary 下方会显示 **Profile check**：长度、章节、数字是否出自原文、原句比例、是否用到"总是采用"的原文章节——全部由代码测量，不额外调用模型。

在项目对话里，回答下方的 **Add to knowledge base** 菜单：
- **Save as example summary**：把这个回答保存为样本（对话里的文件和回答引用的项目 context 文档作为源文档），可以直接重新学习
- **Use as summary profile…**：把这个回答编辑后作为 Learned rules

数据保存在 `<项目文件夹>/.workbench/knowledge/`（`examples/<id>/` 含源文件、`summary.md`、`evidence.json`、`notes.json`；`profile.json` 含各版本），随项目文件夹一起复制。

## 生成文件

模型可以直接生成文件：在对话里说"保存成 Word 文件"、"导出成 CSV"等即可；要求起草 summary 时默认生成 Word 文件。回答里先显示文件的文字内容（带可点击的引用），最后是文件卡片，包含文件名、类型、"Preview as saved"（保存后的样子，含 Sources 列表），以及两个按钮：

- **Save to project folder**（仅项目内）：保存到项目文件夹（可以有子目录，如 `drafts/summary.docx`），不能写到项目文件夹之外；同名文件会先询问是否覆盖
- **Download**：通过浏览器下载

支持 `.md`、`.txt`、`.csv`、`.json`、`.docx`、`.xlsx`、`.pptx`。后三种由模型写成 Markdown，保存时在本地转换（不联网）：

- `.docx`（python-docx）：标题、列表、粗体、表格
- `.xlsx`（openpyxl）：每个 `## 标题` 一个工作表，Markdown 表格写成单元格；数字、百分比、金额存成真正的数字；引用放在 "Source" 列
- `.pptx`（python-pptx）：`# 标题` 生成封面页，每个 `## 标题` 一页（16:9），支持多级要点和表格；以 `Notes:` 开头的行写入演讲者备注；内容太多会自动续页（cont.）

保存 `.docx` / `.xlsx` / `.pptx` / `.md` / `.txt` 时，引用 ID 会变成 `[1]`、`[2]`…，并附 **Sources** 列表（Word/Markdown 在文末，Excel 是单独的 Sources 工作表，PPT 是最后的 Sources 页；内容包括文件名、页码、章节和原文摘录），离开本应用也能追溯来源。

实现方式：system prompt 告诉模型用 `<file path="名字.扩展名">…</file>` 包住文件内容（`backend/outputs.py`）。

## 来源定位（M2）

点击回答中的引用标签（如 `D1 · p.2`），右侧会打开 **Source** 面板：

- **PDF**：后端用 PyMuPDF 把对应页渲染成图片并画好高亮——引用的段落用浅黄色标出，**支持这句话的具体句子用深黄色标出**；可以翻页、放大（Fit / 150% / 200%…）。段落跨页时会注明
- **Word / TXT / Markdown**：显示全文，滚动到引用的段落并高亮句子
- 面板顶部是原文摘录（章节路径 + 段落全文，匹配的句子加标记）

**句子是怎么定位的**：模型只给出段落 ID；前端把引用前面那句话（claim）一起传给后端，后端在段落里找出与 claim 词语重合度最高的句子（数字权重更高），再在 PDF 页面上逐词对齐，得到每一行的坐标。一个 claim 对应段落中多句话时会全部标出；没有足够相符的句子时只高亮整段，并在面板中注明。

## Projects

同一类任务（比如 summary drafting）建一个 Project，以后重复使用。左侧 **Projects +** 创建，需要提供：

| 字段 | 作用 |
|---|---|
| **Folder** | 项目的工作目录。项目内的对话只能读取这个文件夹里的文件，**Save to folder** 也只能写到这里（不能写到文件夹外，也不能写进 `.workbench/`）。可以手动填路径，也可以点 Browse… 选择 |
| **Instructions** | 任务说明，自动加进这个项目每个对话的 system prompt |
| **Context** | 背景资料（样本 summary、术语表、模板……），上传、粘贴文本或从项目文件夹添加都可以；每个对话都会带上，引用编号为 C1、C2… |

项目数据保存在 `<folder>/.workbench/`（`project.json` 和 `context/`），所以项目文件夹是自包含的，可以复制给同事。用 New project 选择一个已有 `.workbench` 的文件夹，会**重新打开**这个项目及其 instructions 和 context。“Remove project from app”只是从列表中移除并删除对话，不会删除文件夹。

引用编号：`C*` 是项目 context，`D*` 是当前对话里 attach 的文件。

## 结构

```
start.py         启动器：建 .venv、装依赖、启动服务并打开浏览器
make_package.py  打包成只含允许文件类型的 zip
backend/
  app.py         FastAPI：REST API（/api/*），并挂载界面
  ui.py          界面（NiceGUI，纯 Python）：聊天、文件、Projects、来源面板、设置
  settings.py    设置读写（data/settings.json + 环境变量 / env.txt）
  llm.py         LLM 适配：ollama 原生 / OpenAI 兼容，流式
  files.py       白名单文件夹浏览
  documents.py   通用解析（PDF/DOCX/TXT/MD）、引用句子定位、带高亮的页面渲染
  chats.py       会话存储、prompt 拼装、超长文档的段落筛选
  projects.py    项目：instructions、context、文件夹沙盒、输出写入
  outputs.py     模型生成的文件：解析 <file> 块、Markdown 转 Word
  knowledge.py   知识库：样本、学习 profile（测量 + 分析 + 合并）、pinned 规则、draft 检查
  alignment.py   summary ↔ 原文对齐与测量（出处、覆盖、长度、原句比例、数字）
  citations.py   宽松的引用识别（各种写法都能点击）
data/            运行时数据（git-ignored）：docs/ 解析缓存，chats/ 会话，uploads/ 上传文件
```

> 早期的 React 版界面保留在 git 分支 `feat/m1-chat-ui` 上。

**解析结果**：每个文档存为 `data/docs/<hash>/doc.json`（段落 + 页码 + 坐标，用于在 PDF 中高亮）和 `doc.md`（LLM 看到的格式）。查看某个文件的解析结果：

```bash
.venv/bin/python -m backend.documents path/to/file.pdf
```

## 开发

```bash
.venv/bin/uvicorn backend.app:app --port 8000 --reload
```
