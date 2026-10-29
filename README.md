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

数据保存在 `<项目文件夹>/.workbench/projects/<项目id>/knowledge/`（旧版本建的项目是 `.workbench/knowledge/`；`examples/<id>/` 含源文件、`summary.md`、`evidence.json`、`notes.json`；`profile.json` 含各版本），随项目文件夹一起复制。

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

## 从网页下载文档（From web）

右上角 **From web** 打开一个分步骤的流程（项目内外都可以用）：

1. **Web address**：输入网页地址（或直接是一个 PDF 的地址）
2. **Choose documents**：列出这一页上的文档链接（PDF、Word、Excel、PowerPoint、CSV、文本），显示文件名、链接文字、大小；可按类型筛选、全选；指向其他网站的链接会用橙色标出。每个文件右边的 👁 可以**预览**：PDF 显示前 3 页，Word / PowerPoint / 文本显示开头的文字，Excel / CSV 显示前 40 行；预览时文件只临时取到本机读取，看完就删除，预览里也可以直接勾选下载
3. **Save to**：存到项目文件夹（可指定子文件夹，默认 `downloads/`），或用 Browse… 选任意文件夹（含共享盘）；同名文件可选跳过 / 两个都保留 / 替换
4. **Download**：逐个下载，显示进度，可以中途停止
5. **Done**：列出保存的文件和失败原因；可以直接 **Attach to chat** 或 **Add to project context**，之后就能总结并点击引用定位原文

**也可以直接在 chat 里贴链接**，程序按消息的意思决定怎么做（只用第一个网址，规则在 `ui.py` 的 `web_intent`，不调用模型）：

| 消息 | 做什么 |
|---|---|
| 要**下载**（download、下载、grab、"get all the PDFs"…；只说 save / 保存 且没有总结、提取之类的词时也算） | 消息**不发给模型**，对话末尾出现上面的下载步骤卡片（嵌在 chat 里，不弹窗），自动扫描这一页；Attach to chat 之后，消息里除网址以外的文字会放回输入框 |
| 要**读网页**（总结、提取数值、分析、比较、问问题…） | 程序读取这一页（只读这一页，不跟链接），把正文转成 Markdown（标题、段落、列表、**表格**都保留，菜单、页脚、脚本去掉）作为文档 attach 到对话，再把消息发给模型；回答可以引用并点开原文。网址直接是 PDF / Word / 文本时，读的就是这个文件 |
| 只有一个网址 | 文档链接直接 attach；网页链接会问你：**Read the page** 还是 **Download documents from it** |

需要登录的网页（见下）读的时候也一样会弹出登录窗口。下载卡片右上角的 **Read the page instead** 可以改成读网页。

读网页时网页内容会交给模型，网页里可能藏着针对模型的指令。所以程序**不让回答加载任何东西**：回答里的 HTML 和图片只显示为文字（代码块不变），模型就没法把对话内容塞进图片地址发出去；下载也只会从你自己输入的网址开始，模型决定不了。

**安全规则**（这个流程不经过 AI 模型，下载什么由用户自己勾选，所以网页里的内容无法让程序把数据发出去）：

- 只用普通的 GET/HEAD 请求：不执行 JavaScript、不保留 cookie、不提交表单，只读你输入的那一页，不会继续跟链接
- 只接受 http/https；带用户名密码的地址会被拒绝；重定向最多 5 次，每一跳都重新检查
- HTTPS 证书始终验证，用的是系统证书库（Windows 证书存储 / macOS 钥匙串，通过 `truststore`），和浏览器一样信任公司根证书，所以公司内网网站也能打开；证书不被信任的网站会被拒绝
- 只下载文档类型，并检查文件开头确实是该格式（比如登录页面冒充的 "report.pdf" 会被拒绝）
- 文件只写进你选的文件夹（不限制文件大小和个数）
- **Settings → Web**：允许的网站（每行一个，留空 = 你输入的任何网站；`company.com` 也允许 `www.company.com`）、是否使用系统 / 公司代理

### 需要登录的网页（SharePoint、Confluence、内网）

扫描时如果网页要求登录（跳到登录页、出现密码框、或返回 401/403），会自动改用电脑上装的 **Microsoft Edge**（没有就用 Chrome），由 Playwright 控制：

1. 先在后台（不显示窗口）打开网页
2. 需要登录时弹出一个浏览器窗口，你在里面正常登录（SSO、MFA 都可以）；回到原网站后窗口自动关闭，后台带着这次登录继续。如果网站不接受后台浏览器，窗口会保持打开，下载完再关
3. 找文件：
   - **SharePoint 文档库**：通过 SharePoint 自己的 REST 接口列出当前文件夹的文件（不含子文件夹）
   - **Confluence 页面**：列出页面的附件
   - 其他网页：读取 JavaScript 运行后页面里的文档链接
4. 文件由浏览器下载，再做和普通下载一样的检查（类型、文件开头、只写进选定文件夹）

也可以直接点 **Sign in first** 先登录再扫描；普通扫描找不到文档时（比如链接是 JavaScript 生成的），可以点 **Open in the browser** 再试。

- 每次都用一个全新的临时浏览器配置，只存在内存里；流程结束（Close、Another page、关掉卡片或对话框）时浏览器关闭，登录信息不保留，下次需要重新登录
- 密码只在浏览器窗口里输入，程序看不到；AI 模型不参与；Settings → Web 的允许网站规则同样适用
- 不会运行 `playwright install`，也不下载 Playwright 自带的浏览器，只用已安装的 Edge / Chrome

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

**多个项目可以用同一个文件夹**：它们共用文件夹里的文件，但各自有自己的 instructions、context 和知识库。项目数据保存在 `<folder>/.workbench/projects/<项目id>/`（`project.json`、`context/`、`knowledge/`；旧版本建的项目还在 `<folder>/.workbench/` 下，照常使用），所以项目文件夹是自包含的，可以复制给同事。用 New project 选择一个复制来的文件夹、并填**同样的项目名**，会**重新打开**那个项目及其 instructions 和 context；名字不同就新建一个项目。“Remove project from app”只是从列表中移除并删除对话，不会删除文件夹。

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
  outputs.py     模型生成的文件：解析 <file> 块、Markdown 转 Word / Excel / PowerPoint
  knowledge.py   知识库：样本、学习 profile（测量 + 分析 + 合并）、pinned 规则、draft 检查
  alignment.py   summary ↔ 原文对齐与测量（出处、覆盖、长度、原句比例、数字）
  citations.py   宽松的引用识别（各种写法都能点击）
  webfetch.py    从网页下载文档：扫描链接、检查规则、下载；把网页读成 Markdown 给 chat（httpx + lxml）
  preview.py     From web 清单里的文件预览（PDF 页面图片、文字、表格）
  browserfetch.py 需要登录的网页：用已安装的 Edge/Chrome（Playwright）登录、列出文件、下载
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
