"""本地 ASR 模块：B站 playurl API 获取音频流 + faster-whisper 转录。

流程：
1. B站 x/player/playurl 获取 DASH 音频流 URL
2. 下载 .m4s 音频到 /tmp
3. faster-whisper 本地转录（small 模型，Apple Silicon MPS 加速）
4. 转录完成后立即删除临时音频文件
"""

import logging
import os
import tempfile
import time

import requests

logger = logging.getLogger(__name__)

# 使用 HuggingFace 镜像加速模型下载（国内）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
# 禁用 Xet 协议，改用 HTTP 下载（镜像不支持 Xet）
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

WHISPER_MODEL = "small"
WHISPER_DEVICE = "auto"
WHISPER_COMPUTE_TYPE = "auto"

API_PLAYURL = "https://api.bilibili.com/x/player/playurl"


def _api_headers(sessdata: str, user_agent: str) -> dict:
    return {
        "User-Agent": user_agent,
        "Referer": "https://www.bilibili.com",
        "Cookie": f"SESSDATA={sessdata}",
    }


def _get_audio_url(bvid: str, sessdata: str, user_agent: str) -> tuple[str, str]:
    """通过 B站 playurl API 获取最高质量音频流 URL。

    Args:
        bvid: 视频 BV 号
        sessdata: Cookie
        user_agent: User-Agent

    Returns:
        (audio_url, codec) — 例如 ("https://...", "mp4a.40.2")

    Raises:
        RuntimeError: 获取失败
    """
    headers = _api_headers(sessdata, user_agent)

    # 1. 获取 cid
    r = requests.get(
        "https://api.bilibili.com/x/web-interface/view",
        headers=headers,
        params={"bvid": bvid},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"view API 失败: code={data.get('code')} {data.get('message')}")
    cid = data["data"]["cid"]

    # 2. 获取音频流
    r = requests.get(
        API_PLAYURL,
        headers=headers,
        params={
            "bvid": bvid,
            "cid": cid,
            "fnval": 4048,
            "fnver": 0,
            "fourk": 1,
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"playurl API 失败: code={data.get('code')} {data.get('message')}")

    dash = data["data"].get("dash", {})
    audios = dash.get("audio", [])
    if not audios:
        raise RuntimeError("视频无音频流")

    # 取最高码率
    best = max(audios, key=lambda a: a.get("bandwidth", 0))
    url = best.get("base_url", "")
    if not url:
        # 尝试 backup_url
        backups = best.get("backup_url", [])
        url = backups[0] if backups else ""

    if not url:
        raise RuntimeError("音频 URL 为空")

    codec = best.get("codecs", "unknown")
    return url, codec


def download_audio(url: str, bvid: str, sessdata: str, user_agent: str) -> str:
    """下载音频流到临时文件。

    Args:
        url: 音频流 URL
        bvid: 视频 BV 号
        sessdata: Cookie
        user_agent: User-Agent

    Returns:
        临时文件路径

    Raises:
        RuntimeError: 下载失败
    """
    output_path = os.path.join(tempfile.gettempdir(), f"bilibili_asr_{bvid}.m4s")

    headers = {
        "User-Agent": user_agent,
        "Referer": f"https://www.bilibili.com/video/{bvid}",
        "Cookie": f"SESSDATA={sessdata}",
        "Range": "bytes=0-",  # 有些 CDN 需要
    }

    logger.info(f"下载音频: {bvid}")
    r = requests.get(url, headers=headers, stream=True, timeout=120)
    r.raise_for_status()

    total = 0
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                total += len(chunk)

    file_size = os.path.getsize(output_path)
    logger.info(f"音频已下载: {output_path} ({file_size / 1024 / 1024:.1f}MB)")
    return output_path


def transcribe(audio_path: str) -> str:
    """faster-whisper 语音转文字。

    Args:
        audio_path: 音频文件路径

    Returns:
        带时间戳的转录文本
    """
    from faster_whisper import WhisperModel

    logger.info(f"加载 Whisper 模型 ({WHISPER_MODEL})...")
    model = WhisperModel(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
    )

    logger.info(f"开始转录: {audio_path}")
    segments, info = model.transcribe(
        audio_path,
        beam_size=5,
        language="zh",
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    lines = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            timestamp = time.strftime("%M:%S", time.gmtime(segment.start))
            lines.append(f"[{timestamp}] {text}")

    result = "\n".join(lines)
    logger.info(
        f"转录完成: {len(lines)} 段, {len(result)} 字, "
        f"语言: {info.language} (概率: {info.language_probability:.2f})"
    )
    return result


def transcribe_video(bvid: str, sessdata: str, user_agent: str) -> str:
    """完整 ASR 流程：获取音频流 → 下载 → 转录 → 清理。

    Args:
        bvid: 视频 BV 号
        sessdata: B站 Cookie
        user_agent: User-Agent

    Returns:
        转录文本
    """
    audio_path = None
    try:
        logger.info(f"[{bvid}] 获取音频流 URL...")
        url, codec = _get_audio_url(bvid, sessdata, user_agent)
        logger.info(f"[{bvid}] 音频: {codec}")

        audio_path = download_audio(url, bvid, sessdata, user_agent)
        text = transcribe(audio_path)
        return text
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            logger.info(f"[{bvid}] 已清理音频: {os.path.basename(audio_path)}")
