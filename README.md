# 微信 AI 自动回复机器人 (macOS)

Mac 微信 AI 自动回复机器人，支持私聊自动回复、群聊 @回复、人格切换、消息去重。

> ⚠️ **注意**：本项目仅供学习和个人自动化研究使用，请遵守微信服务条款。

---

## 🔧 解密数据库来源

本项目使用的微信数据库解密工具来自：
- **来源**：https://github.com/zmqzz/wechat-decrypt-mac
- **作者**：zmqzz
- **原理**：通过 Mach API 扫描微信进程内存提取 SQLCipher 3 密钥

详细解密教程见 [USAGE.md](./USAGE.md)

---

## 功能特性

- ✅ 私聊自动回复
- ✅ 群聊 @回复
- ✅ 人格切换 (!人格)
- ✅ 消息去重（30秒内相同内容不重复回复）
- ✅ 消息合并（5秒内连续消息合并为一条回复）
- ✅ AI 智能回复（MiniMax API）

---

## 环境要求

- macOS + 微信 3.8.x
- Python 3.10+
- MiniMax API Key

## 安装

```bash
# 克隆项目
git clone https://github.com/895981398/OMG.git
cd OMG

# 安装依赖
pip install -r requirements.txt
```

## 配置

编辑 `config.py` 或设置环境变量：

```bash
export MINIMAX_KEY="your-api-key"
export MY_WXID="your-wxid"
export DECRYPTED_DIR="./decrypted"
export KEYS_FILE="./all_keys.json"
export WAL_BASE="/Users/xxx/Library/Containers/com.tencent.xinWeChat/..."
```

## 运行

```bash
# 启动机器人
python3 main.py

# 或使用脚本
bash start.sh
```

## 命令

- `!人格` - 查看/切换人格
- 发送消息自动触发 AI 回复
