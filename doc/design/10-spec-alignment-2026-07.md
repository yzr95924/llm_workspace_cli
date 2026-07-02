# 10 · SPEC 对齐：wiki-spec 0.10.0 + workspace-spec 0.3.0

> 本章节集中记录本次"按 spec 最新版本对齐 CLI 实现"的全部变更。
> 它是 [02-wiki-crud.md](02-wiki-crud.md) / [04-data-model.md](04-data-model.md) /
> [05-templates-submodule.md](05-templates-submodule.md) 三份章节的 delta 文档。
>
> | 维度 | spec 版本 | CLI 拉到的 spec 版本（本次之前） | CLI 升到的 spec 版本（本次之后） |
> |---|---|---|---|
> | `llm-wiki-management` | 0.10.0（2026-07-02） | 0.5.0 | **0.10.0** |
> | `llm-workspace-management` | 0.3.0（2026-07-01） | 0.2.0 | **0.3.0** |
>
> 本文件不重复 spec 原文；每条改动给出 spec § 定位 + 改动的代码位置 + 验收要点。

---

## 10.1 背景与边界

### 触发

`my_SKILL` submodule 拉新（提交 `c3bbfa0`），两份 spec 同时升级；CLI 实现落后：

- **会立即报错**：fixtures 文件名错读（`memory-readme.txt` 已不存在，应读 `memory-index.txt`）
- **不会报错但不完整**：workspace init 不建 MEMORY 骨架；wiki init 不建 `wiki/tags.md` / `scripts/SCRIPTS.md`；MEMORY 路径仍在 `wiki/MEMORY/`，spec 0.10.0 要求与 `wiki/` 平级
- **版本号 stale**：CLAUDE.md 与 README 的 spec version 与 SKILL 仓 `metadata.*_spec_version` 不一致

### 范围

| 在范围内 | 不在范围内 |
|---|---|
| wiki init 落盘清单扩到 7 个产物 + 7 子目录 | wiki content page / ingest / query / lint（skill 仓范围） |
| workspace init 加 MEMORY 骨架 1 步 | model registry（已对齐 spec 0.x，09 文档不变） |
| `__init__.py` version 常量同步 bump | ingest workflow / lint checklist（skill 仓 references/ 内已有） |
| `check_not_initialized` 扩展到 5 类产物拒绝 | 老 wiki 迁移通路（spec 0.10.0 §附录 B 注明"老 wiki 由 workspace CLI 自行处理"，本期仅做新建路径，不做 retroactive migration） |
| `doc/design/02 / 04 / 05` 同步更新 | |

### 不复用旧 PR

无前置 PR；本次在 master 上一次性合入（按项目 `MEMORY/test-priority-low.md` 取向，prototype 阶段手动 smoke 验收）。

---

## 10.2 变更总表

7 项改动按代码路径分两组：

| # | 类型 | 文件 | spec § | 改动摘要 |
|---|---|---|---|---|
| 1 | bug fix | `llmw/wiki/init_wiki.py:93` | wiki §5.1 | 读 fixture 名 `memory-readme.txt → memory-index.txt` |
| 2 | version | `llmw/__init__.py:4-5` | workspace §14 / wiki §10 | `WIKI_SPEC_VERSION 0.5.0 → 0.10.0`；`WORKSPACE_SPEC_VERSION 0.2.0 → 0.3.0` |
| 3 | wiki init | `llmw/wiki/init_wiki.py:122-132` | wiki §1 / §5 | MEMORY 从 `wiki/MEMORY/README.md` 迁到 `<wiki>/MEMORY/MEMORY.md`（路径移 wiki 根 + 文件名 MEMORY.md） |
| 4 | wiki init | `llmw/wiki/init_wiki.py` 新增 | wiki §9.1 | 拷 `fixtures/tags.md.txt` → `<wiki>/wiki/tags.md`（无占位符，fixture 与 canonical 字节一致） |
| 5 | wiki init | `llmw/wiki/init_wiki.py` 新增 | wiki §14 | 拷 `fixtures/scripts.md.txt` → `<wiki>/scripts/SCRIPTS.md`（含 `{{TOPIC_NAME}}` 占位符，substitute 后落盘） |
| 6 | init guard | `llmw/wiki/init_wiki.py:check_not_initialized` | wiki §8 | 拒绝条件由 2 个扩到 5 个：新增 `MEMORY/MEMORY.md` / `wiki/tags.md` / `scripts/SCRIPTS.md` |
| 7 | workspace init | `llmw/workspace/manager.py` 新增 `_write_workspace_memory_index` | workspace §9.1 | 拷 `llm-workspace-management/references/fixtures/memory-index.txt` → `<workspace>/MEMORY/MEMORY.md`；helper 在 `init()` 中 `CLAUDE.md` 写入后调用；幂等（已存在跳过） |

**文档侧（与代码同步落盘）**：

| # | 文档 | 章节 | 改动摘要 |
|---|---|---|---|
| D1 | `doc/design/05-templates-submodule.md` | §5.1 fixture 列表 / §5.5 占位符表 / §5.6 fixture 耦合表 | fixture 列表 4→6（+ `tags.md.txt` / `scripts.md.txt`）；占位符表新增 SCRIPTS.md 用 `{{TOPIC_NAME}}`；§5.7 文件依赖图补完 |
| D2 | `doc/design/02-wiki-crud.md` | wiki add 流程 / 产物清单 | 写入清单 + 子目录清单扩到 7 件；流程图加 `wiki/tags.md`、`scripts/SCRIPTS.md`、`<wiki>/MEMORY/MEMORY.md` 三步 |
| D3 | `doc/design/04-data-model.md` | §4 子段（CLI 产物 schema） | 简述 `<wiki>/MEMORY/MEMORY.md` / `<wiki>/wiki/tags.md` / `<wiki>/scripts/SCRIPTS.md` 的"不可变 / 不参与 5 必填 lint"性质 |
| D4 | `doc/design/10-spec-alignment-2026-07.md`（本文档） | 全文新增 | 本次 delta |

---

## 10.3 关键决策与权衡

### D1. `check_not_initialized` 拒绝条件扩到 5 个

**决策**：spec §8 表格只列 `CLAUDE.md` / `wiki/index.md`，但 §8 总段说"绝不允许覆盖已有 wiki"。本项目选择"精神 > 字面"——5 个 CLI 落盘产物任一已存在即拒绝。

**反方案**：仅按 §8 表格保留 2 个拒绝。其余 3 个产物若已存在则覆盖。

**原因**：

1. spec §5.1 / §9.1 / §14 都明确这 3 个产物是"CLI init 时刻写入、后续维护方负责"，覆盖意味着接管 LLM 私有记忆 / tag 白名单 / scripts 索引——这些不该被 init 默默改写
2. 现有失败模式友好（错误信息按文件给出，hint 指"先备份 + 删除"）
3. 改动面小（`check_not_initialized` 已经是 list-of-paths 形态，加 3 行）

### D2. workspace `_write_workspace_memory_index` 幂等

**决策**：`MEMORY.md` 已存在 → 跳过（spec §9.1 "idempotent: 已存在则跳过"）。

**与 workspace.toml / gitignore / CLAUDE.md 三个文件的拒绝策略不一致**：

| 产物 | 已存在 → |
|---|---|
| `workspace.toml` | 拒绝（init 整体因"路径非空"被 `WorkspaceExists` 拦） |
| `CLAUDE.md` | 拒绝（spec §12；用户宪法） |
| `.gitignore` | 块替换（marker 区间 patch，§5.1） |
| **`MEMORY/MEMORY.md`** | **跳过**（spec §9.1） |

**原因**：MEMORY 索引是 LLM agent 私有记录，可能已经写了几条 experience，再 `init` 时不应擦掉。init 重跑是"补骨架"而非"重建"。

### D3. fixtures 字面量权威性冲突：scripts.md.txt vs §14.7 README

**事实**：

- 跑 `head fixtures/scripts.md.txt` → line 1 写了 `# {{TOPIC_NAME}} Scripts`（**有**占位符）
- spec §14.7（迁移段）写："拷贝 `references/fixtures/scripts.md.txt` 到 `scripts/SCRIPTS.md`（无占位符,直接落盘）"
- `fixtures/README.md` line 20 也写："scripts.md.txt ... 无占位符,直接 fixture 比对（与 gitignore 同款）"

**决策**：CLI 走 fixture 字节事实——`{{TOPIC_NAME}}` 替换后落盘（与 `wiki/index.md.txt` / `wiki/log.md.txt` 同流程）。

**理由**：

1. spec §14.3 明确指出 SCRIPTS.md 模板含 `{{TOPIC_NAME}}`，§14.3 是权威
2. fixtures 与 canonical 双双有占位符（spec 锚点渲染流程适用）
3. fixtures/README.md 与 §14.7 的"无占位符"是笔误，应在 spec 仓库改——但这是 SKILL 仓的活，不是 CLI 的

### D4. workspace MEMORY fixture 取 `workspace-spec.md` 仓库

**事实**：

- `llm-wiki-management/references/fixtures/memory-index.txt`：wiki 仓 fixture
- `llm-workspace-management/references/fixtures/memory-index.txt`：workspace 仓 fixture

**两份 fixture 字面量相近但内容不同**（顶部 1 行说明文本区分于自己的 spec / SKILL）。

**决策**：workspace init 走 `llm-workspace-management` 子模块的 fixture，**不**复读 wiki 仓。

**原因**：spec §9.1 显式区分 wiki / workspace 两份 MEMORY 索引路径；引用的链接是 workspace 的 spec / SKILL；少一次跨 skill 耦合。

### D5. 不写老 wiki 迁移通路

**决策**：spec 0.9.0 / 0.10.0 升级路径中"老 wiki 自动 migration"**不**实现。

**理由**：

- spec §附录 B 多次注明："已 init 的 X.Y 老 wiki 不自动迁移（`--check-version --apply` 不为此出 legacy pattern）"
- 迁移是 skill 仓 `scripts/lint_wiki.py --check-version --apply` 的工作，不归 workspace CLI
- prototype 阶段范围最小化

### D6. 命名约束要点

| 文件名 | 大小写 | 原因 |
|---|---|---|
| `MEMORY/` | **大写** | spec §1（区别于小写 `raw` / `wiki` / `scripts`） |
| `MEMORY.md` | **大写** | 与目录名同 source；`fixtures/README.md` 显式约定 |
| `SCRIPTS.md` | **大写** | scripts 索引；同 MEMORY.md 形态 |
| `tags.md` | **小写** | wiki 内目录是 `wiki/`，跟同级 `index.md` / `log.md` 同小写 |

CLI 落盘路径直接走 fixture 字面量，无新约束。

---

## 10.4 实施步骤（按依赖顺序）

> 步骤编号不强制，依赖图关键路径是：① 读 fixtures → ② 写产物。任意 wiki add / workspace init 现在都跑同一 helper。

### 步骤 1：版本常量 bump（低风险，单独可发）

文件：`llmw/__init__.py:4-5`

```diff
- WORKSPACE_SPEC_VERSION = "0.2.0"  # 对齐 workspace-spec.md
- WIKI_SPEC_VERSION = "0.5.0"  # 对齐 SKILL.md metadata.wiki_spec_version
+ WORKSPACE_SPEC_VERSION = "0.3.0"  # 对齐 workspace-spec.md
+ WIKI_SPEC_VERSION = "0.10.0"  # 对齐 SKILL.md metadata.wiki_spec_version
```

校验：

```bash
python3 -c "from llmw import WIKI_SPEC_VERSION, WORKSPACE_SPEC_VERSION; print(WIKI_SPEC_VERSION, WORKSPACE_SPEC_VERSION)"
# 期望: 0.10.0 0.3.0
```

### 步骤 2：bug fix — fixture 文件名（高频触发，直接报错）

文件：`llmw/wiki/init_wiki.py:93`

```diff
- memory_md_tmpl = (fixtures / "memory-readme.txt").read_text(encoding="utf-8")
+ memory_md_tmpl = (fixtures / "memory-index.txt").read_text(encoding="utf-8")
```

校验：

```bash
TMP=$(mktemp -d)
python -m llmw --workspace $TMP init
python -m llmw --workspace $TMP wiki add smoke --topic "Smoke"
test -f $TMP/smoke/MEMORY/MEMORY.md
```

### 步骤 3：MEMORY 路径迁移（wiki 根 + 文件名 MEMORY.md）

文件：`llmw/wiki/init_wiki.py`

变更点：

1. 目录列表：移除 `wiki/MEMORY`，新增根级 `<wiki>/MEMORY`
2. atomic_write 路径：`wiki/MEMORY/README.md → MEMORY/MEMORY.md`
3. CLAUDE.md 模板里的 `@MEMORY/MEMORY.md` import 行由 submodule 维护，CLI 只负责 MEMORY.md 落盘在匹配位置

```diff
   for d in (
       [wiki_dir / "raw" / x for x in _RAW_SUBDIRS]
       + [wiki_dir / "wiki" / x for x in _CONTENT_SUBDIRS]
-      + [wiki_dir / "wiki" / "MEMORY"]
+      + [wiki_dir / "MEMORY"]
   ):
       d.mkdir(parents=True, exist_ok=True)

   try:
       atomic_write(wiki_dir / "CLAUDE.md", claude_md)
       atomic_write(wiki_dir / ".gitignore", gitignore_tmpl)
       atomic_write(wiki_dir / "wiki" / "index.md", index_md)
       atomic_write(wiki_dir / "wiki" / "log.md", log_md)
-      atomic_write(wiki_dir / "wiki" / "MEMORY" / "README.md", memory_md)
+      atomic_write(wiki_dir / "MEMORY" / "MEMORY.md", memory_md)
```

### 步骤 4：新增 `wiki/tags.md` 渲染

文件：`llmw/wiki/init_wiki.py`

```python
# 在 read 模板段增加:
tags_md_tmpl = (fixtures / "tags.md.txt").read_text(encoding="utf-8")

# mapping 不变（tags.md 无占位符，substitute 是 no-op 占位检测）

# 在 atomic_write 段增加:
atomic_write(wiki_dir / "wiki" / "tags.md", tags_md_tmpl)
```

### 步骤 5：新增 `scripts/SCRIPTS.md` 渲染（含 `{{TOPIC_NAME}}`）

文件：`llmw/wiki/init_wiki.py`

```python
# read:
scripts_md_tmpl = (fixtures / "scripts.md.txt").read_text(encoding="utf-8")

# substitute（mapping 已有 TOPIC_NAME）:
scripts_md = _substitute(scripts_md_tmpl, mapping)

# 在 atomic_write 段增加:
atomic_write(wiki_dir / "scripts" / "SCRIPTS.md", scripts_md)

# 在目录创建段增加:
(wiki_dir / "scripts").mkdir(parents=True, exist_ok=True)
```

### 步骤 6：`check_not_initialized` 拒绝条件扩展

文件：`llmw/wiki/init_wiki.py:29-39`

```python
def check_not_initialized(wiki_dir: Path) -> None:
    """spec §8: 5 类 CLI 落盘产物任一已存在 → 拒绝覆盖

    spec §8 表格列 CLAUDE.md + wiki/index.md 是必检；§8 总段"绝不允许覆盖已有 wiki"
    的精神把范围扩到 MEMORY.md / tags.md / SCRIPTS.md。必须在 mkdir 前调用,避免半成品目录。
    """
    files = [
        wiki_dir / "CLAUDE.md",
        wiki_dir / "wiki" / "index.md",
        wiki_dir / "MEMORY" / "MEMORY.md",       # 0.10.0 新增
        wiki_dir / "wiki" / "tags.md",            # 0.8.0+
        wiki_dir / "scripts" / "SCRIPTS.md",      # 0.9.0+
    ]
    for f in files:
        if f.exists():
            raise WikiAlreadyInitialized(
                f"{f} 已存在,拒绝覆盖",
                hint="若要重新初始化,请先备份 + 删除该文件",
            )
```

### 步骤 7：workspace `_write_workspace_memory_index` 新 helper

文件：`llmw/workspace/manager.py`（在 `_write_workspace_claude_md` 后追加，init() 末尾调用）

```python
def _write_workspace_memory_index(workspace_root: Path) -> None:
    """spec §9.1: 拷 fixtures/memory-index.txt → <workspace>/MEMORY/MEMORY.md。
    索引无 frontmatter、被 <workspace>/CLAUDE.md 用 @MEMORY/MEMORY.md import。
    幂等：已存在则跳过（spec §9.1 idempotent）。
    """
    target = workspace_root / "MEMORY" / "MEMORY.md"
    if target.exists():
        return

    refs = workspace_spec_templates_dir()
    if not refs.is_dir():
        raise SkillMissing(...)
    try:
        content = (refs / "fixtures" / "memory-index.txt").read_text(encoding="utf-8")
    except OSError as e:
        raise SetupFailed(
            f"读取 workspace MEMORY.md fixture 失败: {e.filename}",
            hint="检查 my_SKILL/llm-workspace-management/references/ 是否完整",
        )
    (workspace_root / "MEMORY").mkdir(parents=True, exist_ok=True)
    try:
        atomic_write(target, content)
    except OSError as e:
        raise SetupFailed(...)
```

调用点：`init()` 末尾、`_write_workspace_claude_md(path, display_name)` 之后：

```python
_write_workspace_claude_md(path, display_name)
_write_workspace_memory_index(path)  # 新增
print(f"[llmw] workspace 已初始化于 {path}", ...)
```

### 步骤 D1：D1 文档改动

文件：`doc/design/05-templates-submodule.md`

- §5.1 文件清单加 `fixtures/tags.md.txt` + `fixtures/scripts.md.txt`，目录树由 4→6
- §5.5 占位符表加 SCRIPTS.md 一行（`<wiki>/scripts/SCRIPTS.md` 渲染 `{{TOPIC_NAME}}`）
- §5.6 兼容性约束补"5 份 fixture 字节级稳定（或同步 bump）" → 6 份
- §5.7 文件依赖图补 `fixtures/tags.md.txt` / `fixtures/scripts.md.txt` / `MEMORY/` / `scripts/` 四行
- §附录 A 自检脚本补：

  ```bash
  cmp -s $TMP/<wiki>/MEMORY/MEMORY.md     canonical/memory-index.md
  cmp -s $TMP/<wiki>/wiki/tags.md         fixtures/tags.md.txt
  cmp -s $TMP/<wiki>/scripts/SCRIPTS.md   canonical/...(rendered)
  ```

### 步骤 D2：D2 文档改动

文件：`doc/design/02-wiki-crud.md`

- §add 流程图：原子写段由 5 行→7 行（+ tags.md / SCRIPTS.md / MEMORY.md 移位）
- §产物清单：补 3 个 + 修正 MEMORY 路径
- §拒绝条件表：扩到 5 类
- §git_init 段：`_GITKEEP_SUBDIRS` 不变（MEMORY 不是 5 大内容页子目录，不需 .gitkeep），scripts/ 由 SCRIPTS.md 自然 git track

### 步骤 D3：D3 文档改动

文件：`doc/design/04-data-model.md`

- §4 加 1 小节描述 wiki 端 3 类"不参与 5 必填 lint 的索引产物"（`<wiki>/MEMORY/MEMORY.md`、`<wiki>/wiki/tags.md`、`<wiki>/scripts/SCRIPTS.md`），引 wiki-spec §5.1 / §9.1 / §14
- workspace 端加 1 小节描述 `<workspace>/MEMORY/MEMORY.md` 引 workspace-spec §9.1

---

## 10.5 验收清单（手动 smoke）

按 README §Manual Smoke Test 走一遍，下列检查项为本 PR 增量：

```bash
# 1. workspace init 落盘骨架齐全（10.3 step 7）
TMP=$(mktemp -d)
python -m llmw --workspace $TMP init
ls $TMP  # 应见: workspace.toml / workspace_models.toml / CLAUDE.md / .gitignore / MEMORY/
test -f $TMP/MEMORY/MEMORY.md && echo "✓ workspace MEMORY.md"

# 2. workspace init 幂等（MEMORY.md 已存在跳过;其余拒绝）
python -m llmw --workspace $TMP init
echo "[llmw] workspace 已初始化于 $TMP"  # 已存在 → 应被 WorkspaceExists 拦，不应继续跑

# 3. wiki add 落盘 7 产物
python -m llmw --workspace $TMP wiki add smoke --topic "Smoke"
test -f $TMP/smoke/CLAUDE.md
test -f $TMP/smoke/.gitignore
test -f $TMP/smoke/wiki/index.md
test -f $TMP/smoke/wiki/log.md
test -f $TMP/smoke/MEMORY/MEMORY.md           # 路径正确
test -f $TMP/smoke/wiki/tags.md                # 新增
test -f $TMP/smoke/scripts/SCRIPTS.md          # 新增

# 4. fixtures 字节金标准
diff $TMP/smoke/.gitignore               my_SKILL/llm-wiki-management/references/fixtures/gitignore.txt
diff $TMP/smoke/MEMORY/MEMORY.md        my_SKILL/llm-wiki-management/references/canonical/memory-index.md
diff $TMP/smoke/wiki/tags.md            my_SKILL/llm-wiki-management/references/fixtures/tags.md.txt
diff $TMP/smoke/scripts/SCRIPTS.md      <(sed "s/{{TOPIC_NAME}}/Smoke/g; s/{{SETUP_DATE}}/$(date +%F)/g" my_SKILL/llm-wiki-management/references/fixtures/scripts.md.txt)
diff $TMP/smoke/wiki/index.md           <(sed "s/{{TOPIC_NAME}}/Smoke/g; s/{{SETUP_DATE}}/$(date +%F)/g" my_SKILL/llm-wiki-management/references/fixtures/index.md.txt)
diff $TMP/smoke/wiki/log.md             <(sed "s/{{TOPIC_NAME}}/Smoke/g; s/{{SETUP_DATE}}/$(date +%F)/g" my_SKILL/llm-wiki-management/references/fixtures/log.md.txt)

# 5. CLAUDE.md 占位符干净
test $(grep -c '{{' $TMP/smoke/CLAUDE.md) = 0

# 6. check_not_initialized: 5 类拒绝任一
for f in CLAUDE.md wiki/index.md MEMORY/MEMORY.md wiki/tags.md scripts/SCRIPTS.md; do
    touch $TMP/smoke/$f
    python -m llmw --workspace $TMP wiki add should-not-add --topic "X" 2>&1 | grep -q "拒绝覆盖" || echo "✗ $f 没拦下来"
    rm -f $TMP/smoke/$f
done

rm -rf $TMP
```

### 自动化检查（CI）

```bash
ruff format --check .  # CI lint job
ruff check .           # CI lint job
pytest -q              # CI test job (py3.7 + py3.11)
```

无新测试（`MEMORY/test-priority-low.md`）。

---

## 10.6 风险与回滚

| 风险 | 触发 | 回滚 |
|---|---|---|
| check_not_initialized 拒绝更严格导致老 wiki 不能 `wiki add` 覆盖重 init | 用户对已存在的 MEMORY/tags/SCRIPTS 跑 `wiki add` 而确实想重 init | 现有提示已说"先备份 + 删除"，新加 3 行 hint 同形态 |
| wiki init 失败但 MEMORY/ 已建 | atomic_write 部分失败 | `atomic_write` 已有 try/exit + tmp 清理；MEMORY 父目录是 `mkdir(parents=True, exist_ok=True)`，失败可整段 rollback 到 init 之前状态——但当前 init 失败不回滚；这一点继承现状（prototype 接受） |
| workspace `_write_workspace_memory_index` 在 CLAUDE.md 之后失败 | atomic_write OSError | 与 CLAUDE.md helper 共用 `SetupFailed` 异常；init 整体失败 → 留下 `workspace.toml` + `.gitignore` + 空 `MEMORY/` 目录 + 半截文件——**不**做清理（继承现状） |
| `WIKI_SPEC_VERSION` bump 后已存在 wiki 的 CLAUDE.md §八 `Wiki Spec 版本` 不一致 | 老 wiki 0.5.0 CLAUDE.md 写道 `Wiki Spec 版本 = 0.5.0`，CLI 现在跑出 0.10.0 | 不重渲染老 wiki（spec 不要求），文档层面记录：升级到 0.10.0 后下次手动 rebuild CLAUDE.md 由用户决定 |

无数据迁移风险；无外部脚本兼容性问题（无 `--migrate-*` 类命令被破坏）。

---

## 10.7 文档交叉引用

读取本文件后建议按顺序读：

1. [05-templates-submodule.md](05-templates-submodule.md) — fixture 列表 + 字节金标准流程（本次已更新）
2. [02-wiki-crud.md](02-wiki-crud.md) — `wiki add` 完整流程（本次已更新）
3. [04-data-model.md](04-data-model.md) — 数据模型 + 三类"非内容页"索引产物（本次已更新）
4. spec 原文：
   - `my_SKILL/llm-wiki-management/references/wiki-spec.md` v0.10.0
   - `my_SKILL/llm-workspace-management/references/workspace-spec.md` v0.3.0
5. 根 `CLAUDE.md` 的数据模型与 `MEMORY.md` 索引——本文档归属"delta" 类，与 CLAUDE.md I-1 不变量自洽

---

## 附录 A：变更点逐行（diff）

### A.1 `llmw/__init__.py`

```diff
 __version__ = "0.1.0"
-WORKSPACE_SPEC_VERSION = "0.2.0"  # 对齐 workspace-spec.md
-WIKI_SPEC_VERSION = "0.5.0"  # 对齐 SKILL.md metadata.wiki_spec_version
+WORKSPACE_SPEC_VERSION = "0.3.0"  # 对齐 workspace-spec.md
+WIKI_SPEC_VERSION = "0.10.0"  # 对齐 SKILL.md metadata.wiki_spec_version
```

### A.2 `llmw/wiki/init_wiki.py`

完整 diff 因行数多此处省略，详见 §10.4 步骤 2 / 3 / 4 / 5 / 6。

### A.3 `llmw/workspace/manager.py`

仅新增 `_write_workspace_memory_index` helper 一段（约 25 行）+ init() 末尾调用 1 行。详见 §10.4 步骤 7。

### A.4 文档 (`doc/design/02 / 04 / 05`)

| 文件 | 段落 | 性质 |
|---|---|---|
| `02-wiki-crud.md` | wiki add 流程图 + 产物清单 + 拒绝条件表 | 增量改 |
| `04-data-model.md` | §4 末新增子段"非内容页索引产物" | 增量加 |
| `05-templates-submodule.md` | §5.1 / §5.5 / §5.6 / §5.7 / 附录 A | 多处增量改 |

---

## 附录 B：spec 版本对齐校验

```bash
# 拉新 submodule 后:
cd my_SKILL
grep '^  wiki_spec_version:' llm-wiki-management/SKILL.md        # 期望: wiki_spec_version: 0.10.0
grep '^  workspace_spec_version:' llm-workspace-management/SKILL.md  # 期望: workspace_spec_version: 0.3.0

cd ..
python3 -c "
from llmw import WIKI_SPEC_VERSION, WORKSPACE_SPEC_VERSION
assert WIKI_SPEC_VERSION == '0.10.0', WIKI_SPEC_VERSION
assert WORKSPACE_SPEC_VERSION == '0.3.0', WORKSPACE_SPEC_VERSION
print('spec version aligned')
"
```

任一 assert 失败 = spec / 常量漂移，需重新走 §10.4 步骤 1。
