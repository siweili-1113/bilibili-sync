"""LLM 集成模块：文本清理 + 内容摘要。

支持 OpenAI 兼容 API（OpenAI、DeepSeek、Groq、Ollama 等）。
长文本自动分段处理。
"""

import logging
import time

from openai import OpenAI

from src.config import LLMConfig

logger = logging.getLogger(__name__)

# 分段参数
CHUNK_SIZE = 5000  # 每段字符数
CHUNK_OVERLAP = 500  # 重叠字符数
MAX_CHUNK_TOKENS_ESTIMATE = 6000  # 每段预估 token 数


class LLMError(Exception):
    """LLM API 调用失败。"""

    pass


class LLMProcessor:
    """OpenAI 兼容 API 的文本处理客户端。"""

    def __init__(self, config: LLMConfig):
        """初始化 LLM 客户端。

        Args:
            config: LLMConfig 实例
        """
        if not config.api_key:
            raise LLMError(
                "未配置 LLM_API_KEY。\n"
                "请设置环境变量 LLM_API_KEY 或在 config.yaml 中配置。"
            )

        self.config = config
        self.client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )
        logger.info(f"LLM 客户端已初始化: {config.model} @ {config.base_url}")

    def clean_text(self, raw_text: str) -> str:
        """清理和优化字幕文本。

        添加标点、合理分段、去除口语化重复词。

        Args:
            raw_text: 原始字幕文本

        Returns:
            清理后的文本
        """
        if not raw_text.strip():
            return ""

        prompt = self.config.cleaning_system_prompt
        if not prompt:
            prompt = (
                "你是一个专业的中文文字编辑。请对以下视频字幕进行整理：\n"
                "1. 添加正确的标点符号\n"
                "2. 删除无意义的语气词和重复\n"
                "3. 根据语义合理分段\n"
                "4. 修正明显的错别字\n"
                "5. 保持原文完整含义\n"
                "请直接输出整理后的文本。"
            )

        # 长文本分段处理
        if len(raw_text) > CHUNK_SIZE * 1.5:
            return self._chunked_clean(raw_text, prompt)
        else:
            return self._call_llm(prompt, raw_text)

    def generate_summary(self, cleaned_text: str) -> str:
        """生成内容摘要。

        Args:
            cleaned_text: 清理后的文本

        Returns:
            摘要文本
        """
        if not cleaned_text.strip():
            return "（无内容）"

        prompt = self.config.summary_system_prompt
        if not prompt:
            prompt = (
                "请用中文对以下视频内容生成一个简洁的摘要。\n"
                "列出3-5个核心要点，每个要点以'- '开头，不超过50字。"
            )

        # 长文本先分段摘要再汇总
        if len(cleaned_text) > CHUNK_SIZE * 2:
            return self._chunked_summary(cleaned_text, prompt)
        else:
            return self._call_llm(prompt, cleaned_text)

    def process(self, raw_text: str) -> tuple[str, str]:
        """组合处理：清理 + 摘要。

        Args:
            raw_text: 原始字幕文本

        Returns:
            (cleaned_text, summary)
        """
        logger.info("开始 LLM 文本清理...")
        cleaned = self.clean_text(raw_text)
        logger.info(f"文本清理完成 ({len(cleaned)} 字)")

        logger.info("开始生成摘要...")
        summary = self.generate_summary(cleaned)
        logger.info(f"摘要生成完成 ({len(summary)} 字)")

        return cleaned, summary

    def _call_llm(self, system_prompt: str, user_content: str) -> str:
        """调用 LLM API。

        Args:
            system_prompt: 系统提示
            user_content: 用户内容

        Returns:
            LLM 响应文本
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                )
                content = response.choices[0].message.content
                return content.strip() if content else ""

            except Exception as e:
                logger.warning(f"LLM 调用失败 (第 {attempt + 1} 次): {e}")
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.info(f"等待 {wait}s 后重试...")
                    time.sleep(wait)
                else:
                    raise LLMError(f"LLM 调用失败（已重试 {max_retries} 次）: {e}") from e

        return ""

    def _chunked_clean(self, raw_text: str, system_prompt: str) -> str:
        """分段清理长文本。

        Args:
            raw_text: 原始文本
            system_prompt: 系统提示

        Returns:
            拼接后的清理文本
        """
        chunks = _split_text(raw_text, CHUNK_SIZE, CHUNK_OVERLAP)
        logger.info(f"文本分为 {len(chunks)} 段进行清理")

        results = []
        for i, chunk in enumerate(chunks):
            logger.info(f"  清理第 {i + 1}/{len(chunks)} 段 ({len(chunk)} 字)...")
            try:
                result = self._call_llm(system_prompt, chunk)
                results.append(result)
            except LLMError:
                # 如果某段失败，保留原始文本
                results.append(chunk)
                logger.warning(f"  第 {i + 1} 段清理失败，保留原文")

        return "\n\n".join(results)

    def _chunked_summary(self, cleaned_text: str, system_prompt: str) -> str:
        """分段摘要 + 汇总。

        先对每段生成摘要，再把所有摘要汇总成一个总摘要。

        Args:
            cleaned_text: 清理后的文本
            system_prompt: 摘要 prompt

        Returns:
            总摘要
        """
        chunks = _split_text(cleaned_text, CHUNK_SIZE * 2, CHUNK_OVERLAP)
        logger.info(f"文本分为 {len(chunks)} 段生成摘要")

        summaries = []
        for i, chunk in enumerate(chunks):
            logger.info(f"  摘要第 {i + 1}/{len(chunks)} 段...")
            try:
                s = self._call_llm(system_prompt, chunk)
                summaries.append(s)
            except LLMError:
                summaries.append("（本段摘要生成失败）")

        if len(summaries) == 1:
            return summaries[0]

        # 汇总
        logger.info("  汇总各段摘要...")
        merge_prompt = (
            "以下是一个视频各分段的摘要，请整合成一个总的摘要：\n"
            "列出3-5个核心要点，每个要点以'- '开头，不超过50字。"
        )
        combined = "\n".join(f"段落{i + 1}摘要：{s}" for i, s in enumerate(summaries))
        try:
            return self._call_llm(merge_prompt, combined)
        except LLMError:
            return "\n".join(summaries)


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """将文本分割为带重叠的段落。

    优先在句号、换行等自然断点处分段。

    Args:
        text: 原始文本
        chunk_size: 每段目标字符数
        overlap: 段落间重叠字符数

    Returns:
        文本段落列表
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        # 尝试在自然断点处分段
        if end < len(text):
            # 在 chunk_size 范围内找最后一个句号或换行
            search_start = end - min(200, chunk_size // 4)
            for sep in ["\n\n", "\n", "。", "！", "？", ".", "!", "?"]:
                pos = text.rfind(sep, search_start, end)
                if pos > 0:
                    end = pos + len(sep)
                    break

        chunks.append(text[start:end])
        start = end - overlap if end < len(text) else len(text)

    return chunks
