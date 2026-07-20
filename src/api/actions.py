"""B站写操作 API：添加收藏夹、删除稍后再看。"""

import logging

import requests

from src.config import AppConfig

logger = logging.getLogger(__name__)

FAV_FOLDER_NAME = "稍后再看ai总结后保存"


def _headers(config: AppConfig) -> dict:
    return {
        "User-Agent": config.bilibili.user_agent,
        "Referer": "https://www.bilibili.com",
        "Cookie": f"SESSDATA={config.bilibili.sessdata};bili_jct={config.bilibili.csrf}",
    }


def _csrf(config: AppConfig) -> str:
    return config.bilibili.csrf


def ensure_folder(config: AppConfig) -> int:
    """确保收藏夹存在，返回 mlid。

    如果已存在则复用，不存在则创建。
    """
    headers = _headers(config)
    uid = config.bilibili.uid

    # 先查已有
    r = requests.get(
        "https://api.bilibili.com/x/v3/fav/folder/created/list-all",
        headers=headers,
        params={"up_mid": uid},
        timeout=15,
    )
    r.raise_for_status()
    for f in r.json()["data"].get("list", []):
        if f.get("title") == FAV_FOLDER_NAME:
            logger.info(f"收藏夹已存在: {FAV_FOLDER_NAME} (mlid={f['id']})")
            return f["id"]

    # 创建
    r = requests.post(
        "https://api.bilibili.com/x/v3/fav/folder/add",
        headers=headers,
        data={"title": FAV_FOLDER_NAME, "privacy": 0, "csrf": _csrf(config)},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    if d["code"] != 0:
        raise RuntimeError(f"创建收藏夹失败: code={d['code']} {d.get('message')}")

    mlid = d["data"]["id"]
    logger.info(f"收藏夹已创建: {FAV_FOLDER_NAME} (mlid={mlid})")
    return mlid


def add_to_favorites(config: AppConfig, aid: int, folder_mlid: int) -> bool:
    """将视频添加到指定收藏夹。

    Args:
        config: AppConfig
        aid: 视频 av 号
        folder_mlid: 目标收藏夹 mlid

    Returns:
        成功 True
    """
    headers = _headers(config)
    r = requests.post(
        "https://api.bilibili.com/x/v3/fav/resource/deal",
        headers=headers,
        data={
            "rid": aid,
            "type": 2,
            "add_media_ids": str(folder_mlid),
            "del_media_ids": "",
            "csrf": _csrf(config),
        },
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    if d["code"] != 0:
        logger.warning(f"添加到收藏夹失败: code={d['code']} {d.get('message')}")
        return False
    return True


def remove_from_watch_later(config: AppConfig, aid: int) -> bool:
    """从稍后再看中删除视频。

    Args:
        config: AppConfig
        aid: 视频 av 号

    Returns:
        成功 True
    """
    headers = _headers(config)
    r = requests.post(
        "https://api.bilibili.com/x/v2/history/toview/del",
        headers=headers,
        data={"aid": aid, "csrf": _csrf(config)},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    if d["code"] != 0:
        logger.warning(f"从稍后再看删除失败: code={d['code']} {d.get('message')}")
        return False
    return True
