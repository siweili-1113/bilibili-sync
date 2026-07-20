# 环境记录

## 本会话安装内容（2026-07-20）

### pip 包（清华镜像）
```bash
python3.11 -m pip install --break-system-packages \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  faster-whisper
```

连带安装的依赖：ctranslate2, onnxruntime, huggingface-hub, tokenizers, av

### Whisper 模型
- faster-whisper-small (~500MB) → `~/.cache/huggingface/`
- 首次运行 ASR 自动下载，使用 HF 镜像

---

## 清理

```bash
./cleanup.sh
```

会卸载：faster-whisper, ctranslate2, onnxruntime, huggingface-hub, tokenizers, av

会删除：`~/.cache/huggingface/`（含 ~500MB 模型）、临时音频文件、项目 .db 和 output/

注意：requests, pyyaml, python-dotenv, openai 是项目核心依赖，保留不卸。

---

## 手动清理（如果 script 失败）

```bash
# 卸包
python3.11 -m pip uninstall --break-system-packages -y faster-whisper ctranslate2 onnxruntime huggingface-hub tokenizers av

# 删模型
rm -rf ~/.cache/huggingface/

# 删临时文件
rm -f /tmp/bilibili_asr_*.m4s /tmp/bilibili_cookie_*.txt

# 删项目数据
rm -f bilibili_sync.db bilibili_sync.log
rm -rf output/
```
