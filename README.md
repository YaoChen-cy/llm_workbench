# LLM Workbench

本地运行的 LLM 交互界面（英文 UI）：可以浏览本地文件夹、给对话 attach 多个文件，回答中的每个事实都带来源引用，鼠标悬停即可看到原文。

> 原来的 CIP 月度总结流程移到了 [`cip/`](cip/README.md)，用法不变，只是要先 `cd cip`。M3 会把它改造成第一个 Project。

## 启动

```bash
python start.py        # Windows 用 py start.py
```

首次运行会在 `.venv` 中建 Python 环境并安装 `requirements.txt`（需要 Python 3.10+，以及 pip 能访问 PyPI 或公司镜像；有代理时设置 `HTTPS_PROXY` 或 `PIP_INDEX_URL`），然后自动打开 http://localhost:8000 。可选参数：`--port 8001`、`--no-browser`、`--reinstall`。

**整个应用都是 Python**：界面用 [NiceGUI](https://github.com/zauberzeug/nicegui) 编写（`backend/ui.py`），它的浏览器端文件由 pip 安装，仓库里没有 JS/CSS/HTML 文件，也不需要 Node.js。

**复制到另一台电脑**：运行 `python make_package.py`，生成 `llm-workbench-<日期>.zip`。压缩包只包含 git 跟踪的 `.py .txt .md .pdf .json .docx .xlsx` 文件（约 150 KB），不含 `.venv`、`data/` 和任何 key。

**接入公司 API**：复制 `env.example.txt` 为 `env.txt`，填入 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`，或在 **Settings → Company API** 中填写（key 存在 `data/settings.json`，不会提交到 git，也不会被打包）。默认配置已包含 `x-goog-api-key` 请求头、关闭 SSL 校验、绕过代理，与 notebook 中的写法一致。点 **Save & test connection** 验证。

**本地 Ollama**：Settings → Local Ollama。使用 Ollama 原生接口，这样可以设置 `num_ctx`（上下文窗口）。

**允许访问的文件夹**：Settings → Folders。文件浏览器只能读取这些文件夹（含子文件夹）。

## 功能（M1）

- 多会话聊天，流式输出，可中途 Stop（已生成的部分会保留）
- 两种方式 attach 文件：右侧 **Files** 面板勾选，或 📎 上传；支持 PDF / DOCX / TXT / MD
- 文件 attach 后在这个会话中持续有效，编号 D1、D2…（移除文件后编号不会重排）
- 回答中的引用 `[D1-p2-13]` 显示为 `D1 · p.2` 标签，悬停可看文件名、页码和原文，点击打开来源；模型编造的 ID 显示为红色 `D1 · ?`
- 文档超出上下文预算时，自动保留和问题最相关的段落，回答下方会注明“documents trimmed”

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
data/            运行时数据（git-ignored）：docs/ 解析缓存，chats/ 会话，uploads/ 上传文件
cip/             原 CIP 月度总结流程
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
