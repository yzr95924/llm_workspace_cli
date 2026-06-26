"""llmw remove <name> [--purge] [--yes]（spec §3.4）。"""

import shutil

from wiki_workspace import errors, workspace
from wiki_workspace.commands import _common


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

    wiki_dir = (root / m.wikis[name].path).resolve()

    if args.purge and not args.yes:
        errors.emit_error(
            "purge-requires-confirm",
            "--purge 会删除目录 {}；需配合 --yes".format(wiki_dir),
        )
        return errors.EXIT_USER_ERROR

    del m.wikis[name]
    workspace.save_manifest(root, m)

    if args.purge:
        shutil.rmtree(str(wiki_dir), ignore_errors=False)
        print("Removed wiki '{}' (manifest + directory)".format(name))
    else:
        print("Removed wiki '{}' from manifest (directory kept)".format(name))
    return errors.EXIT_OK
