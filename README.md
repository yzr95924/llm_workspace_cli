# llmw — LLM Workspace CLI

管理一个由 [llm-wiki-management](https://github.com/yzr95924/llm-wiki-management) wiki 组成的 workspace。

## 安装

```bash
pip install -e .
```

## 快速上手

```bash
llmw init                         # 创建 ~/llm_workspace/
llmw add llm-systems --topic "LLM Systems"   # 需要 llm-wiki-management
llmw list                         # 列出 wiki
llmw show llm-systems
llmw enter llm-systems            # 在 wiki 里启动 Claude Code
llmw config llm-systems set model claude-opus-4-8
llmw remove llm-systems --yes
```

完整规格见 `doc/design.md`。

## 并发 / 文件系统

原子写用 tmp + fsync + rename。本地文件系统（ext4、APFS）安全。
**NFS 不安全**——不要对 NFS 挂载的 workspace 跑 `llmw`。
