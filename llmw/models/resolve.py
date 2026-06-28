"""wiki → 最终 ModelEntry 单一查找入口

设计 §9.4。被 enter / show / list / wiki config 校验共同消费。
"""

import sys
from pathlib import Path

from llmw._compat import TOMLDecodeError
from llmw.errors import (
    ModelDefaultNotSet,
    ModelNotInRegistry,
    SchemaVersionUnsupported,
    WikiDirMissing,
    WikiNotFound,
)
from llmw.models.store import ModelEntry, RegistryMissing, load
from llmw.wiki import store as wiki_store
from llmw.workspace import store as ws_store


def resolve_for_wiki(workspace_root: Path, wiki_name: str) -> ModelEntry:
    """返回 enter 时该 wiki 实际使用的 ModelEntry。

    优先级：
      1. wiki_metadata.model （若存在）→ 必须在 registry 中
      2. registry 中 is_default=true 的唯一条目

    异常：
      WikiNotFound:        wiki 不在 workspace.toml 中
      WikiDirMissing:      wiki 子目录缺失
      RegistryMissing:     registry 文件不存在（被内部转换为 ModelDefaultNotSet）
      ModelNotInRegistry:  wiki.model 引用了 registry 中不存在的 model_id
      ModelDefaultNotSet:  registry 空或无 is_default=true
      ModelDefaultAmbiguous: 多条 is_default=true（数据损坏, load 时抛）
    """
    ws = ws_store.load(workspace_root)
    if wiki_name not in ws.wikis:
        raise WikiNotFound(
            f"wiki '{wiki_name}' 不在当前 workspace 中",
            hint="运行 `llmw list` 查看已注册 wiki",
        )

    wiki_dir = workspace_root / ws.wikis[wiki_name].path
    if not wiki_dir.is_dir():
        raise WikiDirMissing(
            f"wiki 子目录不存在: {wiki_dir}",
            hint="可能被外部 rm；可 `git checkout` 恢复或重新 add",
        )

    meta = None
    meta_p = wiki_dir / "wiki_metadata.toml"
    if meta_p.is_file():
        try:
            meta = wiki_store.load(wiki_dir)
        except (SchemaVersionUnsupported, OSError, TOMLDecodeError) as e:
            print(
                f"[llmw] warning: 无法读取 wiki_metadata.toml: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            meta = None

    try:
        # load 对 "有 models 但无 default" 不抛错 (default 可后置); wiki 若指定了 model,
        # 即使 registry 无 default 也能用 (走下面的 wiki.model 分支)。
        # 多条 default 仍抛 ModelDefaultAmbiguous, 无 registry 抛 RegistryMissing。
        reg = load(workspace_root)
    except RegistryMissing as e:
        # 用户体验：直接说 ModelDefaultNotSet，不要暴露 RegistryMissing
        raise ModelDefaultNotSet(
            str(e.message),
            hint="运行 `llmw model add --model-id ... --name ... --base-url ... --api-key ... --default` 初始化 registry",
        )

    # wiki 指定了 model → 必须存在
    if meta is not None and meta.model:
        if meta.model not in reg.models:
            raise ModelNotInRegistry(
                f"wiki '{wiki_name}' 引用了不存在的 model_id '{meta.model}'",
                hint="运行 `llmw model list` 查看可用 model_id, 或用 `llmw wiki --name=<name> config unset model` 走默认",
            )
        return reg.models[meta.model]

    # fallback 到默认（lenient load: 多条 default 已抛 ModelDefaultAmbiguous; 无 default
    # 时 reg 内 is_default 全 False, 走到这里 defaults 为空 → 报 ModelDefaultNotSet）
    defaults = [m for m in reg.models.values() if m.is_default]
    if not defaults:
        raise ModelDefaultNotSet(
            "registry 中没有 is_default=true 的条目",
            hint="运行 `llmw model set-default --model-id <ID>` 标记默认",
        )
    return defaults[0]
