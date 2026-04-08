#!/bin/bash
cd ~/.openclaw/workspace/wechat-ai-reply-bot
python3 main.py > /tmp/wechat_bot.log 2>&1 &
echo "✅ 微信机器人已启动，PID: $!"
