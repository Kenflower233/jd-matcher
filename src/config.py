"""配置加载：从.env或环境变量读取API配置。"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    timeout: int = 60
    max_retries: int = 2
    public_deployment: bool = False
    daily_llm_call_limit: int = 120


@dataclass(frozen=True)
class DeploymentConfig:
    public: bool = False
    session_action_limit: int = 5
    daily_llm_call_limit: int = 120


def _read_int(name: str, default: int, minimum: int) -> int:
    """读取整数环境变量，并在配置错误时给出可操作的提示。"""
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} 必须是整数，当前值为：{raw!r}") from e
    if value < minimum:
        raise RuntimeError(f"{name} 不能小于 {minimum}，当前值为：{value}")
    return value


def _read_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(
        f"{name} 必须是 true/false、1/0、yes/no 或 on/off，当前值为：{raw!r}"
    )


def load_deployment_config() -> DeploymentConfig:
    """读取公开部署开关与额度保护；本地运行默认关闭公开模式。"""
    load_dotenv()
    return DeploymentConfig(
        public=_read_bool("PUBLIC_DEPLOYMENT", False),
        session_action_limit=_read_int("PUBLIC_SESSION_ACTION_LIMIT", 5, 1),
        daily_llm_call_limit=_read_int("PUBLIC_DAILY_LLM_CALL_LIMIT", 120, 1),
    )


def load_config() -> Config:
    """加载配置，缺少API Key时抛出明确错误。"""
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "未找到 DEEPSEEK_API_KEY，请在项目根目录创建 .env 文件：\n"
            "DEEPSEEK_API_KEY=你的密钥"
        )
    deployment = load_deployment_config()
    return Config(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        timeout=_read_int("DEEPSEEK_TIMEOUT", 60, 1),
        max_retries=_read_int("DEEPSEEK_MAX_RETRIES", 2, 0),
        public_deployment=deployment.public,
        daily_llm_call_limit=deployment.daily_llm_call_limit,
    )
