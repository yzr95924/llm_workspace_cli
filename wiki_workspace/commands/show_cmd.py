"""llmw show <name> — wiki 详情（spec §3.5）。log/index 经 _compat 软依赖。"""

from wiki_workspace import _compat, errors
from wiki_workspace.commands import _common

_COUNT_SUBDIRS = ("sources", "concepts", "entities", "comparisons", "syntheses")


def _counts(wiki_root):
    out = {}
    for sub in _COUNT_SUBDIRS:
        d = wiki_root / "wiki" / sub
        out[sub] = len(list(d.glob("*.md"))) if d.is_dir() else 0
    return out


def _recent_log(wiki_root, n=5):
    log = wiki_root / "wiki" / "log.md"
    if not log.is_file():
        return []
    lines = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.startswith("## ["):
            lines.append(line)
    return lines[-n:]


def run(args):
    try:
        m = _common.load_manifest(args)
        root = _common.resolve_root(args)
    except errors.CommandError as exc:
        return exc.exit_code

    name = args.name
    if name not in m.wikis:
        errors.emit_error("wiki-not-found", "wiki '{}' 不存在".format(name), hint="llmw list")
        return errors.EXIT_USER_ERROR

    w = m.wikis[name]
    wiki_root = (root / w.path).resolve()

    print("Wiki: {}".format(name))
    print("Path:        {}".format(wiki_root))
    print("Display:     {}".format(w.display_name))
    print("Description: {}".format(w.description))
    model_src = "wikis.{}.model".format(name) if w.model else "workspace.default_model"
    print("Model:       {} (from {})".format(w.effective_model(m.default_model), model_src))
    print("Created:     {}".format(w.created))
    print("Tags:        {}".format(", ".join(w.tags)))

    skill_root = _compat.find_skill_root(workspace_root=root)
    if skill_root is None:
        errors.emit_warn("llm-wiki-management 未找到；跳过 log/index/counts 段")
        return errors.EXIT_OK

    _compat.configure(skill_root)
    entries = _recent_log(wiki_root)
    if entries:
        print()
        print("─── Recent log entries ───")
        for e in entries:
            print(e)

    counts = _counts(wiki_root)
    print()
    print("─── Counts ───")
    print("  ".join("{}: {}".format(k, v) for k, v in counts.items()))
    return errors.EXIT_OK
