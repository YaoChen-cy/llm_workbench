# LLM Workbench

本地运行的 LLM 交互界面（英文 UI）：可以浏览本地文件夹、给对话 attach 多个文件，回答中的每个事实都带来源引用，鼠标悬停即可看到原文。

> 原来的 CIP 月度总结流程移到了 [`cip/`](cip/README.md)，用法不变，只是要先 `cd cip`。M3 会把它改造成第一个 Project。

## 启动

```bash
./start.sh            # macOS / Linux：首次运行会自动建 venv、装依赖、构建前端
start.bat             # Windows（改了前端代码后需删除 frontend\dist 重新构建）
```

然后打开 http://localhost:8000 。

**接入公司 API**：复制 `.env.example` 为 `.env`，填入 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`，或在 UI 的 **Settings → Company API** 中填写（key 存在 `data/settings.json`，不会提交到 git）。默认配置已包含 `x-goog-api-key` 请求头、关闭 SSL 校验、绕过代理，与 notebook 中的写法一致。点 **Save & test connection** 验证。

**本地 Ollama**：Settings → Local Ollama。使用 Ollama 原生接口，这样可以设置 `num_ctx`（上下文窗口）。

**允许访问的文件夹**：Settings → Folders。文件浏览器只能读取这些文件夹（含子文件夹）。

## 功能（M1）

- 多会话聊天，流式输出，可中途 Stop（已生成的部分会保留）
- 三种方式 attach 文件：右侧 **Files** 面板勾选、📎 上传、拖拽到对话区；支持 PDF / DOCX / TXT / MD
- 文件 attach 后在这个会话中持续有效，编号 D1、D2…（移除文件后编号不会重排）
- 回答中的引用 `[D1-p2-13]` 显示为 `D1 · p.2` 标签，悬停可看文件名、页码、章节和原文；模型编造的 ID 显示为红色 `D1 · ?`
- 文档超出上下文预算时，自动保留和问题最相关的段落，回答下方会注明“documents trimmed”

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
backend/
  app.py         FastAPI 路由（/api/*），同时托管 frontend/dist
  settings.py    设置读写（data/settings.json + 环境变量覆盖）
  llm.py         LLM 适配：ollama 原生 / OpenAI 兼容，流式
  files.py       白名单文件夹浏览
  documents.py   通用解析：PDF（标题/段落/表格/页眉页脚/跨页段落）、DOCX、TXT/MD，按文件 hash 缓存
  chats.py       会话存储、prompt 拼装、超长文档的段落筛选
  projects.py    项目：instructions、context、文件夹沙盒、输出写入
frontend/        React + Vite + TypeScript
data/            运行时数据（git-ignored）：docs/ 解析缓存，chats/ 会话，uploads/ 上传文件
cip/             原 CIP 月度总结流程
```

**解析结果**：每个文档存为 `data/docs/<hash>/doc.json`（段落 + 页码 + 坐标，M2 用于在 PDF 中高亮）和 `doc.md`（LLM 看到的格式）。查看某个文件的解析结果：

```bash
.venv/bin/python -m backend.documents path/to/file.pdf
```

## 开发

```bash
.venv/bin/uvicorn backend.app:app --port 8000 --reload     # 后端
cd frontend && npm run dev                                 # 前端 http://localhost:5173（/api 代理到 8000）
```
