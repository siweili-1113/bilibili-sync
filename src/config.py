"""配置加载模块：YAML 文件 + 环境变量覆盖。"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


# 加载 .env 文件（如果存在）
load_dotenv()


@dataclass
class BilibiliConfig:
    """B站 API 配置。"""

    sessdata: str = ""
    csrf: str = ""  # bili_jct，用于 POST/WRITE 操作的 CSRF 校验
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    uid: int = 0  # 在 auth.validate_cookie() 后填充


@dataclass
class LLMConfig:
    """LLM API 配置。"""

    provider: str = "openai_compatible"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.3
    cleaning_system_prompt: str = ""
    summary_system_prompt: str = ""


@dataclass
class SyncConfig:
    """同步行为配置。"""

    favorite_folder_ids: list[int] = field(default_factory=list)
    rate_limit_min: float = 1.0
    rate_limit_max: float = 3.0
    max_retries: int = 3


@dataclass
class OutputConfig:
    """输出配置。"""

    base_dir: str = "./output"


@dataclass
class DatabaseConfig:
    """数据库配置。"""

    path: str = "./bilibili_sync.db"


@dataclass
class LoggingConfig:
    """日志配置。"""

    level: str = "INFO"
    file: str = ""


@dataclass
class AppConfig:
    """应用总配置。"""

    bilibili: BilibiliConfig = field(default_factory=BilibiliConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _env_override(yaml_value: str | int | float | list | None, env_key: str) -> str | int | float | list | None:
    """用环境变量覆盖 YAML 值。

    Args:
        yaml_value: YAML 中的原始值
        env_key: 环境变量名

    Returns:
        覆盖后的值
    """
    env_value = os.environ.get(env_key)
    if env_value is None or env_value == "":
        return yaml_value
    # 类型转换
    if isinstance(yaml_value, int):
        return int(env_value)
    if isinstance(yaml_value, float):
        return float(env_value)
    if isinstance(yaml_value, list):
        # 逗号分隔的列表
        return [int(x.strip()) for x in env_value.split(",") if x.strip()]
    return env_value


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """加载配置：先读 YAML，再用环境变量覆盖敏感字段。

    Args:
        config_path: YAML 配置文件路径

    Returns:
        AppConfig 实例
    """
    config = AppConfig()

    # 尝试加载 YAML
    yaml_path = Path(config_path)
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        if "bilibili" in raw:
            b = raw["bilibili"]
            config.bilibili.sessdata = _env_override(b.get("sessdata", ""), "BILIBILI_SESSDATA")
            config.bilibili.csrf = _env_override(b.get("csrf", ""), "BILIBILI_CSRF")
            config.bilibili.user_agent = b.get("user_agent", config.bilibili.user_agent)

        if "llm" in raw:
            l = raw["llm"]
            config.llm.provider = l.get("provider", config.llm.provider)
            config.llm.api_key = _env_override(l.get("api_key", ""), "LLM_API_KEY")
            config.llm.base_url = _env_override(l.get("base_url", config.llm.base_url), "LLM_BASE_URL")
            config.llm.model = _env_override(l.get("model", config.llm.model), "LLM_MODEL")
            config.llm.max_tokens = l.get("max_tokens", config.llm.max_tokens)
            config.llm.temperature = l.get("temperature", config.llm.temperature)
            config.llm.cleaning_system_prompt = l.get("cleaning_system_prompt", "")
            config.llm.summary_system_prompt = l.get("summary_system_prompt", "")

        if "sync" in raw:
            s = raw["sync"]
            config.sync.favorite_folder_ids = s.get("favorite_folder_ids", [])
            config.sync.rate_limit_min = s.get("rate_limit_min", config.sync.rate_limit_min)
            config.sync.rate_limit_max = s.get("rate_limit_max", config.sync.rate_limit_max)
            config.sync.max_retries = s.get("max_retries", config.sync.max_retries)

        if "output" in raw:
            config.output.base_dir = raw["output"].get("base_dir", config.output.base_dir)

        if "database" in raw:
            config.database.path = raw["database"].get("path", config.database.path)

        if "logging" in raw:
            lg = raw["logging"]
            config.logging.level = lg.get("level", config.logging.level)
            config.logging.file = lg.get("file", config.logging.file)

    # 纯环境变量覆盖（即使没有 YAML）
    if not config.bilibili.sessdata:
        config.bilibili.sessdata = os.environ.get("BILIBILI_SESSDATA", "")
    if not config.bilibili.csrf:
        config.bilibili.csrf = os.environ.get("BILIBILI_CSRF", "")
    if not config.llm.api_key:
        config.llm.api_key = os.environ.get("LLM_API_KEY", "")

    return config
