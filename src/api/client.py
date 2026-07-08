"""限速 HTTP 客户端：B站 API 调用的统一入口。

特性：
- 每次请求前随机延时 1-3 秒
- 请求失败自动重试（指数退避）
- 统一响应校验（code != 0 视为错误）
- CDN 请求跳过 Referer 头
"""

import logging
import random
import time

import requests

from src.config import BilibiliConfig

logger = logging.getLogger(__name__)

API_BASE = "https://api.bilibili.com"


class APIError(Exception):
    """B站 API 返回错误。"""

    def __init__(self, code: int, message: str, endpoint: str = ""):
        self.code = code
        self.message = message
        self.endpoint = endpoint
        super().__init__(f"[{endpoint}] code={code}: {message}")


class BilibiliClient:
    """限速 HTTP 客户端，封装 B站 API 调用。"""

    def __init__(
        self,
        config: BilibiliConfig,
        rate_limit_min: float = 1.0,
        rate_limit_max: float = 3.0,
        max_retries: int = 3,
    ):
        """初始化客户端。

        Args:
            config: B站配置
            rate_limit_min: 最小请求间隔（秒）
            rate_limit_max: 最大请求间隔（秒）
            max_retries: 最大重试次数
        """
        self.config = config
        self.rate_limit_min = rate_limit_min
        self.rate_limit_max = rate_limit_max
        self.max_retries = max_retries
        self._last_request_time = 0.0

    @property
    def _headers(self) -> dict:
        """API 请求通用请求头。"""
        return {
            "User-Agent": self.config.user_agent,
            "Referer": "https://www.bilibili.com",
            "Cookie": f"SESSDATA={self.config.sessdata}",
        }

    def _rate_limit(self) -> None:
        """请求间随机延时，模拟正常使用节奏。"""
        elapsed = time.time() - self._last_request_time
        min_delay = self.rate_limit_min
        if elapsed < min_delay:
            sleep_time = random.uniform(min_delay, self.rate_limit_max)
            logger.debug(f"限速等待 {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        """发送 GET 请求到 B站 API。

        Args:
            endpoint: API 路径（如 /x/web-interface/nav）
            params: URL 查询参数

        Returns:
            API 响应的 data 字段

        Raises:
            APIError: API 返回非 0 状态码（非重试型错误）
            requests.RequestException: 网络错误（已重试后仍失败）
        """
        url = f"{API_BASE}{endpoint}" if not endpoint.startswith("http") else endpoint

        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                self._rate_limit()

                if attempt > 0:
                    wait = min(2 ** (attempt - 1), 60)
                    logger.info(f"重试第 {attempt} 次，等待 {wait}s...")
                    time.sleep(wait)

                resp = requests.get(
                    url,
                    params=params,
                    headers=self._headers,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

                code = data.get("code", -1)
                if code != 0:
                    msg = data.get("message", "未知错误")
                    # 某些错误码可以重试（如 -412 被拦截，-509 请求过于频繁）
                    if code in (-509, -412, -504) and attempt < self.max_retries:
                        logger.warning(f"可重试错误 [{endpoint}] code={code}: {msg}")
                        last_exception = APIError(code, msg, endpoint)
                        continue
                    raise APIError(code, msg, endpoint)

                return data.get("data", {})

            except requests.Timeout as e:
                logger.warning(f"请求超时 [{endpoint}], 第 {attempt + 1} 次尝试")
                last_exception = e
            except requests.ConnectionError as e:
                logger.warning(f"连接错误 [{endpoint}], 第 {attempt + 1} 次尝试")
                last_exception = e
            except requests.HTTPError as e:
                status_code = e.response.status_code if e.response else 0
                if status_code in (429, 502, 503) and attempt < self.max_retries:
                    logger.warning(f"HTTP {status_code} [{endpoint}], 第 {attempt + 1} 次尝试")
                    last_exception = e
                    continue
                raise
            except APIError:
                raise

        raise last_exception  # type: ignore[misc]

    def download_raw(self, url: str) -> list[dict]:
        """下载 CDN 资源（字幕 JSON），不需要 Referer 头。

        Args:
            url: 完整 URL（会自动补 https: 前缀）

        Returns:
            解析后的 JSON 数据

        Raises:
            requests.RequestException: 网络错误
        """
        if url.startswith("//"):
            url = f"https:{url}"

        headers = {
            "User-Agent": self.config.user_agent,
            # CDN 请求不需要 Referer 和 Cookie
        }

        self._rate_limit()
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
