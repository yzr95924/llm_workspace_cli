"""llmw 自定义异常 + 错误格式化"""

from typing import Optional


class LlmwError(Exception):
    """所有 CLI 异常的基类"""

    exit_code: int = 1
    user_message: str = ""

    def __init__(self, message: Optional[str] = None, hint: Optional[str] = None):
        self.message = message or self.user_message
        self.hint = hint
        super().__init__(self.message)


# ===== 用户错误 (exit_code = 1) =====


class WorkspaceNotFound(LlmwError):
    exit_code = 1
    user_message = "未找到 workspace 根"


class WorkspaceExists(LlmwError):
    exit_code = 1
    user_message = "目标路径已存在且非空"


class WikiNotFound(LlmwError):
    exit_code = 1
    user_message = "wiki 不在当前 workspace 中"


class WikiExists(LlmwError):
    exit_code = 1
    user_message = "wiki 名重复"


class WikiAlreadyInitialized(LlmwError):
    """spec §8: 目标目录已含 CLAUDE.md 或 wiki/index.md,拒绝覆盖"""
    exit_code = 1
    user_message = "wiki 目录已初始化"


class WikiDirMissing(LlmwError):
    exit_code = 1
    user_message = "wiki 子目录缺失"


class PurgeRequiresConfirmation(LlmwError):
    exit_code = 1
    user_message = "非 TTY 下 --purge 需要 --yes 确认"


class InvalidConfigKey(LlmwError):
    exit_code = 1
    user_message = "config KEY 不在白名单"


class KeyNotUnsettable(LlmwError):
    exit_code = 1
    user_message = "KEY 不可 unset"


class ConfigKeyMissing(LlmwError):
    exit_code = 1
    user_message = "config get KEY 不存在"


class MissingRequiredFlag(LlmwError):
    exit_code = 1
    user_message = "非 TTY 下 metadata 字段缺 flag"


class SchemaVersionUnsupported(LlmwError):
    exit_code = 1
    user_message = "schema_version 不被当前 CLI 支持"


class InvalidWikiName(LlmwError):
    exit_code = 1
    user_message = "wiki 名格式非法"


class InvalidTagValue(LlmwError):
    exit_code = 1
    user_message = "tag 值非法"


# ===== 环境错误 (exit_code = 2) =====


class SkillMissing(LlmwError):
    exit_code = 2
    user_message = "SKILL submodule 未初始化"


class SetupFailed(LlmwError):
    """wiki 初始化失败:模板缺失、渲染异常、atomic_write 失败等"""
    exit_code = 2
    user_message = "wiki 初始化失败"


class BackupFailed(LlmwError):
    """wiki remove --purge 前的备份步骤失败(mv / mkdir 任一失败)

    备份失败时不动 wiki;用户可加 --no-backup 跳过备份直接删。
    """
    exit_code = 2
    user_message = "wiki 备份失败"


class ClaudeNotFound(LlmwError):
    exit_code = 2
    user_message = "claude 不在 PATH"


class GitUnavailable(LlmwError):
    exit_code = 2
    user_message = "git 不可用"


class PythonUnavailable(LlmwError):
    exit_code = 2
    user_message = "sys.executable 不可执行"


# ===== model registry 错误 (exit_code = 1) =====


class ModelNotInRegistry(LlmwError):
    exit_code = 1
    user_message = "wiki 引用了不存在的 model_id"


class ModelDefaultNotSet(LlmwError):
    exit_code = 1
    user_message = "workspace 没有默认 model"


class ModelDefaultAmbiguous(LlmwError):
    exit_code = 1
    user_message = "registry 存在多条 is_default=true, 数据损坏"


class ModelIdConflict(LlmwError):
    exit_code = 1
    user_message = "model_id 已存在"


class ModelIsDefault(LlmwError):
    exit_code = 1
    user_message = "目标 model 是默认, 不能直接 remove"


class InvalidModelField(LlmwError):
    exit_code = 1
    user_message = "model 字段值非法"


class RegistryMissing(LlmwError):
    exit_code = 1
    user_message = "workspace_models.toml 不存在"


class OverlayFileUnparseable(LlmwError):
    exit_code = 1
    user_message = "overlay 文件不是合法 JSON"


# ===== 内部错误 (exit_code = 3) =====


class InternalError(LlmwError):
    exit_code = 3
    user_message = "未预期的内部错误"


def format_error(err: LlmwError, debug: bool = False) -> str:
    """渲染为 [llmw] error: ... / [llmw] hint: ... 格式"""
    lines = [f"[llmw] error: {err.message}"]
    if err.hint:
        lines.append(f"[llmw] hint: {err.hint}")
    if debug:
        import traceback

        lines.append("[llmw] traceback:")
        lines.append(traceback.format_exc())
    return "\n".join(lines)
