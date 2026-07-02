# git hooks（仓库内、可复现）

启用后由 `core.hooksPath` 指向本目录，`git` 会用这里的 hook 取代 `.git/hooks`。

```bash
bash scripts/install-hooks.sh     # 启用（设 core.hooksPath = scripts/git-hooks）
bash scripts/uninstall-hooks.sh   # 停用（恢复默认 .git/hooks）
```

## pre-push

推送前把 `my_SKILL` submodule 更新到 `.gitmodules` 配置分支（`master`）的远端最新：

- **已是最新** → 放行 push。
- **落后** → `git submodule update --remote` 把工作树更到最新，然后**中止本次
  push**，提示先 `git add my_SKILL && git commit` 再 push。

为什么中止而不自动提交并推送：pre-push 触发时本次要推送的 commit 集合已冻结，
submodule 指针 bump 是一处未提交改动，无法并入这次 push。守卫式中止保证永不推送
落后的 submodule 指针，也不偷偷改写历史。

子模块未初始化时 hook 直接跳过，不阻断 push。
