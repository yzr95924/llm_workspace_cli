# 05 · SKILL `references/` 字节金标准 + Submodule 集成

本章规范 CLI 与 SKILL submodule 的边界（spec 0.2.0 后的新模型）：

- CLI **内联实现** wiki 仓创建（不再调 subprocess）
- CLI 读 SKILL `references/` 下的模板与 fixtures 作为**字节金标准**
- SKILL 仓只管"出生后的运行时纪律"（ingest / lint / query）

---

## 5.1 SKILL `references/` —— CLI 字节金标准

**位置**：`my_SKILL/llm-wiki-management/references/`（submodule 内）

**性质**：CLI 的 **字节级字面量来源**；SKILL 仓维护，CLI 消费

### 文件清单

```
my_SKILL/llm-wiki-management/references/
├── claude-md-template.md          # CLAUDE.md 拷贝模板 (占位符: 4 个)
├── wiki-spec.md                   # CLI 实现契约 (wiki-spec v0.3.0)
├── fixtures/
│   ├── index.md.txt               # wiki/index.md 字面量 (占位符: 2 个)
│   ├── log.md.txt                 # wiki/log.md 字面量 (占位符: 2 个)
│   ├── memory-readme.txt          # wiki/MEMORY/README.md 字面量 (占位符: 2 个)
│   └── gitignore.txt              # .gitignore 字面量 (无占位符)
├── ingest-workflow.md
├── lint-checklist.md
├── page-templates.md
├── paper-wiki-profile.md
└── query-workflow.md
```

CLI 只读前 6 份（template + 4 fixtures + 1 spec 文档参考）；其余是 SKILL session 内的 LLM 参考资料。

### 角色分工

| 文件 | 谁生成 | 何时变更 |
|---|---|---|
| `claude-md-template.md` | SKILL 仓维护 | 用户改 schema 时同步；CLI 拷贝时按 §10 替换 4 占位符 |
| `fixtures/*.txt` | SKILL 仓维护（人类编辑） | 与 `wiki-spec.md` 同步；CLI 字节比对金标准（cmp -s） |
| `wiki-spec.md` | SKILL 仓维护 | CLI 实现契约；本仓 I-1 / I-2 不变量与此同步 |

### 验证流程（附录 A）

```bash
TMP=$(mktemp -d)
llmw --workspace $TMP init
llmw --workspace $TMP wiki add mywiki --topic "Test"
cmp -s $TMP/mywiki/wiki/index.md              my_SKILL/.../fixtures/index.md.txt
cmp -s $TMP/mywiki/wiki/log.md                 my_SKILL/.../fixtures/log.md.txt
cmp -s $TMP/mywiki/wiki/MEMORY/README.md       my_SKILL/.../fixtures/memory-readme.txt
cmp -s $TMP/mywiki/.gitignore                  my_SKILL/.../fixtures/gitignore.txt
# CLAUDE.md: 4 占位符替换干净 (内容级, 不能 cmp)
test $(grep -c '{{' $TMP/mywiki/CLAUDE.md) = 0
```

任一 cmp 不一致 = CLI 实现 bug。

### 升级流程

1. SKILL 仓改 fixtures / template（人类编辑）；同时 bump `metadata.wiki_spec_version`
2. CLI 仓拉新 submodule 后跑附录 A 自检；不一致即同步升级 CLI 渲染逻辑或对齐 fixtures
3. CLI 仓同时 bump `llmw.WIKI_SPEC_VERSION` 常量（spec §10）

---

## 5.2 本仓 `templates/`（仅 wiki_metadata.toml 模板）

**位置**：CLI 仓库根目录（`templates/`）

**性质**：git 入库；CLI 自己维护

### 文件清单

```
templates/
└── wiki_metadata.toml.template    # wiki add 时拷出实例的源
```

### 角色

- 仅承载 **wiki_metadata.toml** 的 schema 模板（`04-data-model.md` §4.3）
- **不**承载 CLAUDE.md / index.md / log.md / MEMORY/README / .gitignore —— 这些一律走 SKILL `references/`
- 由 `llmw.wiki.store.create_skeleton()` 消费

### 维护规则

- 模板文件由 CLI 维护者修改，**不**自动同步到已存在的 wiki 实例
- 升级路径：CLI 升级 + 用户手动 `llmw wiki config ...`
- **不做自动迁移**（Phase 1 简化版）

---

## 5.3 SKILL Submodule 集成

**位置**：`my_SKILL/llm-wiki-management/`（CLI 仓库根目录下的 submodule）

**性质**：git submodule，指向 `@my_SKILL/llm-wiki-management` 的某个 tag 或 commit

### 为什么用 submodule

- **版本固定**：CLI 与 SKILL 的版本可以独立演进，但运行时锁住当前 commit
- **零打包成本**：CLI 不打包 SKILL 内容；用户 clone CLI 仓后跑 `git submodule update --init` 拉取
- **API 稳定**：CLI 只通过 **文件路径** 读 SKILL `references/`；SKILL 内部任何运行时纪律（ingest / lint / query）不影响 CLI
- **离线友好**：submodule 一旦初始化，渲染不需要重新下载

### `.gitmodules` 引用

```ini
[submodule "my_SKILL/llm-wiki-management"]
    path = my_SKILL/llm-wiki-management
    url = https://github.com/yzr95924/my_SKILL.git
    branch = main
```

### 用户拉取 CLI 时

```bash
git clone https://github.com/yzr95924/llmw.git
cd llmw
git submodule update --init --recursive    # 必须, 否则 SkillMissing
```

README 必须明确写出 submodule 初始化步骤；否则 `wiki add` 报 `SkillMissing`。

---

## 5.4 SKILL references/ 路径解析

`llmw.wiki.init_wiki` 读模板与 fixtures 时的路径定位：

| 来源 | 说明 |
|---|---|
| `llmw.config.wiki_spec_templates_dir()` | 返回 `<repo>/my_SKILL/llm-wiki-management/references/` |

无 env var 覆盖（旧 `$LLMW_SKILL_SETUP_SCRIPT` 已废弃）。

### 路径解析逻辑

```python
def wiki_spec_templates_dir() -> Path:
    return repo_root() / "my_SKILL" / "llm-wiki-management" / "references"
```

`repo_root()` = `Path(__file__).resolve().parent.parent.parent`（`llmw/config.py` → `llmw/` → `<repo>/`）。

### 失败处理

| 场景 | 异常 | 提示 |
|---|---|---|
| `references/` 目录缺失 | `SkillMissing` | "请运行 `git submodule update --init` 初始化 SKILL" |
| `fixtures/` 目录缺失 | `SetupFailed` | "检查 SKILL 仓 references/fixtures/ 是否完整" |
| 模板 / fixture 文件读失败（OSError） | `SetupFailed` | "检查 SKILL submodule 是否完整" |
| 占位符残留（assert 失败） | `SetupFailed` | "检查 mapping 是否覆盖所有占位符" |

---

## 5.5 渲染契约（spec §10 / §11）

CLI 在 `render_and_write` 中做以下替换（4 占位符全替换，assert 无残留）：

| 占位符 | 替换为 | 来源 |
|---|---|---|
| `{{TOPIC_NAME}}` | `topic` 参数 | `add(topic=...)` |
| `{{SETUP_DATE}}` | `date.today().isoformat()` | 当天日期 |
| `{{WIKI_SPEC_VERSION}}` | `llmw.WIKI_SPEC_VERSION` | 常量（对齐 SKILL `metadata.wiki_spec_version`） |
| `{{CLI_VERSION}}` | `llmw.__version__` | `__init__.py` 常量 |

`.gitignore` fixture **无占位符**，直接落盘。

### 版本号双轨对齐

- SKILL `metadata.wiki_spec_version`（如 `0.3.0`）
- CLI `llmw.WIKI_SPEC_VERSION` 常量（同步 bump）
- 升级时两者必须保持一致；不一致 = SKILL 仓已升 spec 而 CLI 未跟

---

## 5.6 SKILL 版本管理

### 锁定策略

- CLI 仓 `.gitmodules` 锁定 SKILL 的 branch / commit
- 推荐：CLI 仓库根 commit 把 submodule 锁到 SKILL 的某个 tag（如 `wiki-spec-v0.3.0`）
- 这样 CLI 的每个 release 对应固定的 spec 版本

### 升级流程

1. SKILL 仓 bump `metadata.wiki_spec_version` + 改 fixtures / template
2. CLI 仓拉新 submodule 后跑附录 A 自检；不一致即同步升级 CLI 渲染逻辑或对齐 fixtures
3. CLI 仓同时 bump `llmw.WIKI_SPEC_VERSION` 常量

### 兼容性约束

CLI 与 SKILL 的耦合**仅**在以下文件路径与字节字面量：

- `<repo>/my_SKILL/llm-wiki-management/references/claude-md-template.md`
- `<repo>/my_SKILL/llm-wiki-management/references/fixtures/*.txt`

只要 SKILL 维持：

- 4 个 fixtures 字节级稳定（或与 CLI `WIKI_SPEC_VERSION` 同步 bump）
- CLAUDE.md 模板维持 4 占位符 `{{TOPIC_NAME}}` / `{{SETUP_DATE}}` / `{{WIKI_SPEC_VERSION}}` / `{{CLI_VERSION}}`
- `wiki/MEMORY/README.md` fixture 维持（spec §5.1 字面量）

CLI 与 SKILL 即兼容。SKILL 内部任何运行时纪律（ingest / lint / query）变更不影响 CLI。

---

## 5.7 文件依赖图

```
CLI 仓库根
├── bin/llmw                          # CLI 可执行入口
├── llmw/                             # CLI Python 包
│   ├── wiki/
│   │   ├── init_wiki.py              # render_and_write + check_not_initialized
│   │   ├── git_init.py               # --git opt-in (spec §7)
│   │   └── manager.py                # add → init_wiki + git_init
│   └── ...
├── templates/
│   └── wiki_metadata.toml.template   # 仅 wiki_metadata.toml schema 模板
├── my_SKILL/                         # git submodule (来自 my_SKILL 仓)
│   └── llm-wiki-management/
│       ├── SKILL.md
│       ├── scripts/                  # CLI 不调用; SKILL session 内用
│       │   ├── ingest_diff.py
│       │   └── lint_wiki.py
│       └── references/
│           ├── claude-md-template.md # ← CLI 拷贝源
│           ├── wiki-spec.md          # CLI 实现契约
│           ├── fixtures/
│           │   ├── index.md.txt      # ← CLI 字节金标准
│           │   ├── log.md.txt
│           │   ├── memory-readme.txt
│           │   └── gitignore.txt
│           └── ...
├── doc/
├── MEMORY/
└── pyproject.toml
```

| 文件 / 目录 | 由谁提供 | 何时更新 |
|---|---|---|
| `bin/llmw` | CLI 仓 | 跟随 CLI release |
| `llmw/` | CLI 仓 | 跟随 CLI release |
| `templates/wiki_metadata.toml.template` | CLI 仓 | 跟随 CLI release |
| `my_SKILL/.../references/claude-md-template.md` | SKILL 仓（submodule） | 用户 `git submodule update` 拉新 |
| `my_SKILL/.../references/fixtures/*.txt` | SKILL 仓（submodule） | 用户 `git submodule update` 拉新 |
| `my_SKILL/.../references/wiki-spec.md` | SKILL 仓（submodule） | spec 版本对齐时拉新 |

---

## 5.8 与 build / install 的关系

CLI 安装脚本只关心 `bin/llmw` + Python 包，不涉及 submodule 与 templates：

- `bin/llmw` 复制到 `~/.local/bin/llmw`
- `llmw` Python 包安装到目标 site-packages（或以可编辑模式安装）
- `templates/` 跟随 Python 包一起安装（数据文件）
- `my_SKILL/` submodule **不**被打包——用户使用时由 CLI 自己从本地路径读（submodule 已经初始化了）

如果将来 CLI 要支持 wheel 安装场景，需考虑：

- 把 `claude-md-template.md` + 4 fixtures 作为 package data 一起打包
- `wiki_spec_templates_dir()` 改为支持回退到 packaged data
- （当前缺陷：详见 `MEMORY/test-priority-low.md` 与 pyproject 已知 wheel 缺陷）

---

## 5.9 历史变更（spec 0.2.0）

| 之前（≤ 0.1.0） | 现在（0.2.0+） |
|---|---|
| CLI 调 `python my_SKILL/.../scripts/setup_wiki.py`（subprocess） | CLI 自己 `read fixture` + `str.replace` + `atomic_write` |
| `SkillScriptMissing` 异常 | 删除（不再有"脚本缺失"概念） |
| `$LLMW_SKILL_SETUP_SCRIPT` env 覆盖 | 删除（路径固定，无 env） |
| `templates/CLAUDE.md.template`（CLI 仓） | 删除（CLAUDE.md 走 SKILL `references/claude-md-template.md`） |
| 默认强制 git add + commit 提示 | 默认不碰 git；`--git` opt-in；失败也不阻断 |
| `wiki/MEMORY/` 不存在 | spec §5 新增（0.2.0） |

任何把 `setup_wiki.py` 写回 SKILL 仓的尝试都属"逆转 spec 演化方向"，不予支持。