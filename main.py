#!/usr/bin/env python3
"""
微信 AI 自动回复机器人 - 主程序入口
"""
import os, sys, fcntl, time, subprocess, threading
import core

# ====== PID 锁，防止多开 ======
PID_FILE = '/tmp/wechat_bot.pid'
f_pid = open(PID_FILE, 'w')
try:
    fcntl.flock(f_pid.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    f_pid.write(str(os.getpid()))
    f_pid.flush()
    os.fsync(f_pid.fileno())
except BlockingIOError:
    print("❌ 机器人已在运行中，退出", flush=True)
    sys.exit(0)


def start_daemon_thread(target, name):
    def wrapper():
        while True:
            try:
                target()
            except Exception as e:
                core.log(f"❌ {name} 线程崩溃: {e}，5秒后重启")
                time.sleep(5)
    t = threading.Thread(target=wrapper, daemon=True, name=name)
    t.start()
    core.log(f"✅ {name} 线程启动")

def main():
    core.log("=" * 60)
    core.log("微信 AI 自动回复机器人")
    core.log("发送 !人格 查看/切换人格")
    core.log("=" * 60)

    start_daemon_thread(core.poll_messages, "消息接收")
    start_daemon_thread(core.process_messages, "AI处理")
    start_daemon_thread(core.send_replies, "消息发送")
    start_daemon_thread(core.check_pending_messages, "合并检查")

    core.log("4个线程已启动")

    try:
        while True:
            if core.wechat_activated and core.last_message_time > 0:
                if int(time.time()) - core.last_message_time > core.config.WECHAT_CLOSE_DELAY:
                    subprocess.run(
                        ['osascript', '-e', 'tell app "System Events" to set frontmost of process "WeChat" to false'],
                        capture_output=True, timeout=5
                    )
                    core.wechat_activated = False
                    core.log("微信已隐藏到后台")
            time.sleep(10)
    except KeyboardInterrupt:
        core.log("\n停止")
    finally:
        os.unlink(PID_FILE)

if __name__ == "__main__":
    main()
