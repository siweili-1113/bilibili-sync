# ASR 环境记录

## 安装的 pip 包（通过清华镜像）
```bash
python3.11 -m pip install --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple yt-dlp faster-whisper
```

| 包 | 版本 | 用途 |
|---|---|---|
| yt-dlp | 2026.7.4 | 下载 B站视频音频流 |
| faster-whisper | 1.2.1 | 本地语音转文字 |
| ctranslate2 | 4.8.1 | faster-whisper 的推理引擎 |
| torch | (自动安装) | 深度学习框架 |
| huggingface-hub | 1.22.0 | 模型下载管理 |

## 下载的模型

- **Whisper small** (~500MB) → `~/.cache/huggingface.co/hub/models--Systran--faster-whisper-small/`
- 首次运行时自动下载，使用 `HF_ENDPOINT=https://hf-mirror.com` 镜像

## HuggingFace 镜像

```bash
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_ENABLE_HF_TRANSFER=0   # 禁用 Xet 加速（镜像不支持）
export HF_HUB_DISABLE_XET=1          # 强制使用 HTTP 下载
```

## 清理方法

运行 `./cleanup.sh`
