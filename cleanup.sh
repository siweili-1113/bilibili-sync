#!/bin/bash
# B站同步工具 - ASR 环境清理脚本
# 卸载所有 ASR 相关依赖，删除下载的模型

set -e

echo "=== B站同步工具 ASR 环境清理 ==="
echo ""

# 1. 卸载 pip 包
echo ">>> 卸载 pip 包..."
pip3 uninstall -y yt-dlp faster-whisper ctranslate2 onnxruntime huggingface-hub tokenizers av 2>/dev/null || python3.11 -m pip uninstall --break-system-packages -y yt-dlp faster-whisper ctranslate2 onnxruntime huggingface-hub tokenizers av 2>/dev/null
echo "  完成"

# 2. 删除 Whisper 模型
echo ">>> 删除 Whisper 模型..."
rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-small/
echo "  完成"

# 3. 删除临时音频文件（如果有残留）
echo ">>> 清理临时音频..."
rm -f /tmp/bilibili_asr_*.m4a /tmp/bilibili_asr_*.mp3 /tmp/bilibili_asr_*.webm 2>/dev/null
echo "  完成"

echo ""
echo "=== 清理完成 ==="
echo ""
echo "注意: torch (PyTorch) 未被卸载，因为可能被其他项目使用。"
echo "如需完全卸载 torch: pip3 uninstall torch -y"
