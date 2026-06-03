# 中文优先 LLM Wiki

这是一个面向 LLM Agent 的知识库脚手架，用于把原始资料逐步编译成可维护、可交叉引用、以中文为主的 Markdown Wiki。

## 致谢与参考

这个项目的整体思路参考了 Andrej Karpathy 的想法文件：[karpathy/llm-wiki.md](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)。

## 核心原则

1. `raw/` 只保存原始来源及其附件，保持原语言、不可变。
2. `wiki/` 是唯一的知识编译层，所有结论、总结与结构化页面默认使用中文。
3. `wiki/` 页面文件名使用稳定的 ASCII slug，页面标题与正文使用中文。
4. 关键论断优先采用“中文综合 + 原文短摘录 + `raw/` 路径”的写法，方便追溯。

## 目录结构

```text
.
├── AGENTS.md
├── README.md
├── llm-wiki.md
├── raw/
├── templates/
│   ├── analysis-page.md
│   ├── entity-page.md
│   ├── lint-report.md
│   ├── source-page.md
│   └── topic-page.md
└── wiki/
    ├── analyses/
    ├── entities/
    ├── index.md
    ├── log.md
    ├── overview.md
    ├── sources/
    └── topics/
```

## Git 与隐私

- 这个公开版本默认不跟踪 `raw/` 中的原始资料。
- `wiki/sources/`、`wiki/topics/`、`wiki/entities/`、`wiki/analyses/` 默认也不纳入版本控制，避免把个人知识库内容直接上传到公开仓库。
- 如果你未来想把其中一部分公开，请自行调整 `.gitignore` 与提交流程。

## 三层架构

### `raw/`

- 只放原始来源文件与来源附件。
- `raw/` 是用户的随手收藏库，可以按自己的习惯自由组织。
- 可以按主题、项目、来源、时间或任何个人方式分类，例如 `raw/金融/`、`raw/科技/`、`raw/读书/`；也可以完全不分类，直接把文件放在 `raw/` 根目录。
- `raw/` 的目录结构不承担语言规范职责；来源语言由 LLM 在 ingest 时识别，并记录到对应来源页的 `source_language` 字段。
- LLM 只能读取 `raw/`，不能修改、重命名、移动或删除真实来源文件。
- 若目录中存在 `.gitkeep` 之类占位文件，它们仅用于保留目录结构，不属于来源材料。

### `wiki/`

- 这是唯一的 canonical 知识层。
- LLM 在这里维护中文摘要、主题综合、实体页、分析页、索引与日志。
- 所有新知识应先写入 `wiki/`，而不是回写到 `raw/`。

### `AGENTS.md`

- 这是 LLM 的行为规范与工作流说明。
- 当你用 Codex 或其他 Agent 维护这个仓库时，应先读取该文件，再执行 ingest、query 或 lint。

## 最短工作流

### Ingest

1. 把原始资料放入 `raw/` 下任意你喜欢的位置。
2. 让 LLM 先读取 `wiki/index.md`、`wiki/overview.md`、相关页面与该来源文件。
3. LLM 在 `wiki/sources/` 新建或更新中文来源页。
4. LLM 同步更新相关 `wiki/topics/`、`wiki/entities/` 页面。
5. LLM 必须更新 `wiki/index.md` 与 `wiki/log.md`。

### Query

1. 让 LLM 先从 `wiki/index.md` 定位相关页面。
2. 基于现有 wiki 页面回答问题，并回指来源页。
3. 若结果具有长期价值，归档到 `wiki/analyses/`。
4. 若有归档，追加一条 `wiki/log.md` 记录。

### Lint

1. 定期让 LLM 检查中文页面之间是否一致。
2. 找出孤儿页、断链、缺少来源支撑的论断。
3. 标记被新来源修正、挑战或覆盖的旧结论。
4. 将检查结果写成一份 lint 报告，必要时补记到 `wiki/log.md`。

## 页面与元数据约定

所有 wiki 页面 frontmatter 键名统一使用英文，避免工具兼容问题。

### 通用字段

- `title`
- `title_zh`
- `page_type`
- `status`
- `updated`
- `tags`

### 来源页附加字段

- `source_title`
- `source_language`
- `raw_path`
- `ingested_on`

### 综合页附加字段

- `source_count`
- `canonical_language: zh`

## 命名与证据约定

- `wiki/` 文件名一律使用 ASCII slug，例如 `model-context-window.md`。
- 页面 H1 一律使用中文标题。
- 原始标题保存在 frontmatter 或“原始标题”区块，不放进文件名。
- Wiki 内部链接优先使用别名形式，例如 `[[model-context-window|模型上下文窗口]]`，兼顾 ASCII 文件名与中文显示名。
- 中文结论后优先附原文短摘录与 `raw/` 路径。
- 如果需要翻译，只在中文解释中转述，不改写原始摘录本身。

## 初次使用建议

- 先把任意来源文件放入 `raw/`，可以分类也可以不分类。
- 让 LLM 依据 `templates/` 模板完成第一次 ingest。
- 完成后检查：
  - `raw/` 文件是否保持不变
  - `wiki/sources/` 是否生成中文来源页
  - `wiki/index.md`、`wiki/log.md` 是否同步更新
  - 关键论断是否附有原文短摘录与 `raw` 路径
