"""工具函数：文件名清理、时间格式化、日志配置。"""

import logging
import re
import sys
from pathlib import Path


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """移除文件名中的非法字符，截断过长名称。

    Args:
        name: 原始文件名
        max_length: 最大字符数（不含扩展名）

    Returns:
        清理后的安全文件名
    """
    # 移除非法字符
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    # 替换多个连续空格
    name = re.sub(r"\s+", " ", name)
    # 去除首尾空格和点号
    name = name.strip(" .")
    # 截断
    if len(name) > max_length:
        name = name[:max_length].rsplit(" ", 1)[0]
    return name or "untitled"


def format_duration(seconds: int | None) -> str:
    """将秒数格式化为 HH:MM:SS 或 MM:SS。

    Args:
        seconds: 秒数

    Returns:
        格式化的时间字符串
    """
    if seconds is None:
        return "00:00"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_pub_time(timestamp: int | None) -> str:
    """将 Unix 时间戳转换为 YYYY-MM-DD 格式。

    Args:
        timestamp: Unix 时间戳（秒）

    Returns:
        日期字符串
    """
    if timestamp is None:
        return "未知"
    from datetime import datetime, timezone

    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """配置全局日志。

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_file: 日志文件路径，None 表示只输出到控制台
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def escape_yaml_value(value: str) -> str:
    """为 YAML frontmatter 转义字符串值。

    如果值中包含冒号或特殊字符，用双引号包裹。

    Args:
        value: 原始字符串

    Returns:
        转义后的字符串
    """
    if any(c in value for c in [":", "#", "[", "]", "{", "}", ",", "&", "*", "!", "|", ">", "'", '"', "%", "@", "`"]):
        # 转义内部双引号并包裹
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    # 检查是否需要引号（纯数字、布尔值、空字符串等）
    if not value or value.lower() in ("true", "false", "yes", "no", "null"):
        return f'"{value}"'
    return value
