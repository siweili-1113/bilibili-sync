"""B站认证模块：Cookie 验证 + UID 提取。"""

import logging

import requests

from src.config import BilibiliConfig

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Cookie 无效或已过期。"""

    pass


def validate_cookie(config: BilibiliConfig) -> int:
    """验证 SESSDATA Cookie 是否有效，返回用户 UID。

    调用 B站 nav 接口，检查登录状态。

    Args:
        config: BilibiliConfig 实例

    Returns:
        用户数字 UID (mid)

    Raises:
        AuthError: Cookie 缺失、无效或已过期
    """
    if not config.sessdata:
        raise AuthError(
            "未配置 BILIBILI_SESSDATA。\n"
            "请从浏览器开发者工具中复制 Cookie 的 SESSDATA 字段，\n"
            "设置到环境变量 BILIBILI_SESSDATA 或 config.yaml 中。"
        )

    url = "https://api.bilibili.com/x/web-interface/nav"
    headers = {
        "User-Agent": config.user_agent,
        "Referer": "https://www.bilibili.com",
        "Cookie": f"SESSDATA={config.sessdata}",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise AuthError(f"无法连接 B站 API: {e}")

    code = data.get("code", -1)
    if code != 0:
        msg = data.get("message", "未知错误")
        raise AuthError(
            f"Cookie 验证失败 (code={code}): {msg}\n"
            "SESSDATA 可能已过期，请从浏览器重新获取。\n"
            "获取方法：浏览器打开 bilibili.com → F12 → Application → Cookies → 复制 SESSDATA 的值。"
        )

    nav_data = data.get("data", {})
    is_login = nav_data.get("isLogin", False)
    if not is_login:
        raise AuthError("Cookie 验证失败：未登录状态，请检查 SESSDATA 是否正确。")

    uid = nav_data.get("mid", 0)
    uname = nav_data.get("uname", "未知用户")
    logger.info(f"Cookie 验证成功，用户: {uname} (UID: {uid})")
    return uid
