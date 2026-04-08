import os, json, time, subprocess, requests, threading, sqlite3, warnings, glob, sys, re, atexit, signal
import queue
from queue import Queue, Empty
import config

# 项目根目录（用于相对路径定位）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
warnings.filterwarnings('ignore')


# ====== 全局状态 ======
RUNNING = True
last_message_time = 0
wechat_activated = False

# 消息队列
msg_queue = Queue(maxsize=100)
reply_queue = Queue(maxsize=100)

# 用户合并缓存
user_pending = {}        # {wxid_key: {messages, last_time, pending, mes_local_id, is_group, is_at, sender_wxid, sender}}
user_processing = set()  # 正在AI处理中的用户wxid_key，防止积压
_current_mid = {}         # {wxid_key: mes_local_id} 当前正在AI处理的最新消息ID，旧的一律丢弃
processing_lock = threading.Lock()
pending_lock = threading.Lock()
merge_lock = threading.Lock()

# AI 回复去重（防止并发重复回复）
_recent_reply_keys = {}  # {mes_local_id: timestamp}
_recent_lock = threading.Lock()

# 全局打断标志：被置为 True 时正在处理的 AI 调用立即停止
_interrupt_flag = False


# ====== 日志 ======
def log(msg):
    print(f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}", flush=True)


# ====== 人格配置 ======
def load_personas():
    try:
        with open(config.PERSONA_FILE, 'r') as f:
            data = json.load(f)
            return {p['id']: p for p in data['personas']}, data.get('default', 'xian_zd')
    except Exception as e:
        log(f"人格配置加载失败: {e}")
        return {}, 'xian_zd'

def get_current_persona():
    personas, default_id = load_personas()
    try:
        with open(config.CURRENT_PERSONA_FILE, 'r') as f:
            pid = f.read().strip()
            if pid in personas:
                return personas[pid], pid
    except:
        pass
    if default_id in personas:
        return personas[default_id], default_id
    return None, default_id

def set_persona(persona_id):
    personas, _ = load_personas()
    if persona_id in personas:
        with open(config.CURRENT_PERSONA_FILE, 'w') as f:
            f.write(persona_id)
        return True
    return False

def list_personas():
    personas, _ = load_personas()
    return [(pid, p['name']) for pid, p in personas.items()]


# ====== 持久化 ======
def save_processed(ids):
    os.makedirs(os.path.dirname(config.PROCESSED_FILE), exist_ok=True)
    with open(config.PROCESSED_FILE, 'w') as f:
        json.dump(list(ids), f)

_last_save_time = 0
def save_processed_throttled():
    global _last_save_time
    now = time.time()
    if now - _last_save_time >= 5:
        save_processed(processed_ids)
        _last_save_time = now

# ====== 全局 processed_ids（用于 atexit 保存）======
processed_ids = set()

def load_processed():
    global processed_ids
    try:
        processed_ids = set(json.load(open(config.PROCESSED_FILE)))
    except:
        processed_ids = set()
    return processed_ids

atexit.register(lambda: save_processed(processed_ids))

def load_context():
    try:
        with open(config.CONTEXT_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_context(ctx):
    os.makedirs(os.path.dirname(config.CONTEXT_FILE), exist_ok=True)
    with open(config.CONTEXT_FILE, 'w') as f:
        json.dump(ctx, f, ensure_ascii=False, indent=2)

def add_to_context(wxid, sender_nickname, message):
    ctx = load_context()
    if wxid not in ctx:
        ctx[wxid] = {'nickname': sender_nickname, 'messages': [], 'last_update': time.time()}
    ctx[wxid]['messages'].append({'content': message, 'time': time.time(), 'is_me': False})
    if len(ctx[wxid]['messages']) > 20:
        ctx[wxid]['messages'] = ctx[wxid]['messages'][-20:]
    ctx[wxid]['last_update'] = time.time()
    save_context(ctx)

def get_context_for_wxid(wxid):
    ctx = load_context()
    return ctx.get(wxid, {}).get('messages', [])


# ====== AI 回复 ======
def ai_reply(sender_nickname, message, context_messages):
    persona, persona_id = get_current_persona()
    if not persona:
        log("❌ 未找到人格配置")
        return None

    prompt = persona['prompt'].format(message=message, sender=sender_nickname)
    prompt += f"\n\n用户：{message}\n你："

    for attempt in range(3):
        try:
            resp = requests.post(
                'https://api.minimax.chat/v1/text/chatcompletion_v2',
                headers={'Authorization': f'Bearer {config.MINIMAX_KEY}', 'Content-Type': 'application/json'},
                json={'model': 'MiniMax-M2.7', 'messages': [{'role': 'user', 'content': prompt}],
                      'temperature': 0.5, 'max_tokens': 1024},
                timeout=15
            )
            result = resp.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            if content:
                return content
            if result.get('base_resp', {}).get('status_code') == 2064:
                time.sleep(2 ** attempt)
        except:
            time.sleep(2)
    return None


# ====== 微信窗口操作 ======
def activate_wechat():
    try:
        subprocess.run(["open", "-a", "WeChat"], capture_output=True, timeout=3)
        time.sleep(0.3)
    except Exception as e:
        log(f"激活微信失败: {e}")

def get_input_coords():
    try:
        result = subprocess.run(
            ['osascript', '-e', 'tell application "WeChat" to get bounds of window 1'],
            capture_output=True, text=True, timeout=5
        )
        x1, y1, x2, y2 = [int(x) for x in result.stdout.strip().split(', ')]
        cx = x1 + int((x2 - x1) * 0.345)
        cy = y1 + int((y2 - y1) * 0.843)
        return cx, cy
    except:
        return 754, 877

def search_and_open_chat(nickname_or_wxid):
    try:
        log(f"[搜索] 搜索词={nickname_or_wxid}")
        activate_wechat()
        time.sleep(0.3)
        subprocess.run(['osascript', '-e', 'tell app "System Events" to keystroke "f" using command down'],
                      capture_output=True, timeout=5)
        time.sleep(0.3)
        p = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        p.communicate(nickname_or_wxid.encode('utf-8'))
        time.sleep(0.2)
        subprocess.run(['osascript', '-e', 'tell app "System Events" to keystroke "v" using command down'],
                      capture_output=True, timeout=5)
        time.sleep(0.8)
        subprocess.run(['osascript', '-e', 'tell app "System Events" to keystroke return'],
                      capture_output=True, timeout=5)
        time.sleep(0.3)
        cx, cy = get_input_coords()
        log(f"[搜索] 进入聊天后坐标=({cx},{cy})")
        subprocess.run([config.CLICLICK_BIN, f'c:{cx},{cy}'], capture_output=True, timeout=5)
        time.sleep(0.3)
        log(f"[搜索] 完成")
        return True
    except Exception as e:
        log(f"切换失败: {e}")
        return False

def send_message(text):
    try:
        original = subprocess.run(['pbpaste'], capture_output=True, text=True).stdout or ''
        p = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        p.communicate(text.encode('utf-8'))
        time.sleep(0.2)
        activate_wechat()
        time.sleep(0.3)
        cx, cy = get_input_coords()
        log(f"[发送] 点击坐标=({cx},{cy}) 内容={text[:30]}")
        subprocess.run([config.CLICLICK_BIN, f'c:{cx},{cy}'], capture_output=True, timeout=5)
        time.sleep(0.3)
        subprocess.run(['osascript', '-e', 'tell app "System Events" to keystroke "v" using command down'],
                      capture_output=True, timeout=5)
        time.sleep(0.3)
        subprocess.run(['osascript', '-e', 'tell app "System Events" to keystroke return'],
                      capture_output=True, timeout=5)
        time.sleep(0.3)
        if original.strip():
            p = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
            p.communicate(original.encode('utf-8'))
        log(f"[发送] 完成")
        return True
    except Exception as e:
        log(f"发送失败: {e}")
        return False

def send_reply_to_contact(nickname, text, sender_wxid=None, is_group=False):
    # 私信没有真实 wxid，不处理
    if not is_group:
        if not sender_wxid or sender_wxid == 'wxid_unknown':
            log(f"⛔ 私信wxid未知，不回复 sender_wxid={sender_wxid}")
            return False
        try:
            conn = sqlite3.connect(config.CONTACT_DB, timeout=5)
            c = conn.cursor()
            c.execute("SELECT m_nsAliasName FROM WCContact WHERE m_nsUsrName = ?", (sender_wxid,))
            row = c.fetchone()
            conn.close()
            # alias 查不到就用 wxid 直接搜索（联系人可能没设置微信号）
            lookup_id = row[0] if row and row[0] else sender_wxid
        except Exception as e:
            log(f"查通讯录失败: {e}")
            lookup_id = sender_wxid
        log(f"[发送] 私信 sender_wxid={sender_wxid} lookup_id={lookup_id} 内容={text[:30]}")
        if not search_and_open_chat(lookup_id):
            return False
        time.sleep(0.3)
        return send_message(text)
    else:
        # 群聊不走搜索，直接发
        log(f"[发送] 群聊直接发送 内容={text[:30]}")
        return send_message(text)


# ====== 消息解析 ======
def is_group_message(blob):
    if blob:
        try:
            return '@chatroom' in blob.decode('utf-8', errors='ignore')
        except:
            pass
    return False

def is_at_me(content):
    return f'@{config.MY_WXID}' in content or '@奔跑吧' in content

def extract_sender_from_blob(blob):
    if not blob:
        return "wxid_unknown", "我"
    try:
        blob_str = blob.decode('utf-8', errors='ignore')
        wxid_match = re.search(r'([rw]xid_[a-zA-Z0-9]+)', blob_str)
        if not wxid_match:
            return "wxid_unknown", "我"
        wxid = wxid_match.group(1)
        after_wxid = blob_str[wxid_match.end():]
        for cp in [' : ', ' :', ': ', ':', '　：', '　:', '　', '：', ':']:
            pos = after_wxid.rfind(cp)
            if pos >= 0:
                nickname_part = after_wxid[:pos]
                break
        else:
            nickname_part = after_wxid.strip()
        chinese = re.findall(r'[\u4e00-\u9fff]+', nickname_part)
        if chinese:
            return wxid, chinese[-1]
        printable = re.findall(r'([a-zA-Z0-9]+)', nickname_part)
        if printable:
            nickname = re.sub(r'^(wxid_|r?wxid_)+', '', printable[0])
            if nickname:
                return wxid, nickname
        return wxid, wxid
    except:
        return "wxid_unknown", "我"

def clean_sender(raw_sender):
    if not raw_sender:
        return None, "未知"
    match = re.match(r'^(r?wxid_[a-zA-Z0-9]+)(.*)$', raw_sender)
    if match:
        wxid = match.group(1)
        nickname = match.group(2).strip()
        while nickname and (nickname.startswith('wxid_') or nickname.startswith('_')):
            nickname = nickname[5:] if nickname.startswith('wxid_') else nickname[1:]
            nickname = nickname.strip()
        return (wxid, nickname or wxid)
    return (f"nick_{raw_sender}", raw_sender.strip())


# ====== 线程1：消息轮询 ======
def poll_messages():
    global last_message_time, wechat_activated, RUNNING, processed_ids
    processed_ids = load_processed()
    keys = json.load(open(config.KEYS_FILE))
    sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tools', 'wechat-decrypt'))
    from crypto_params import full_decrypt, decrypt_wal
    poll_count = 0
    last_decrypt_time = 0

    while True:
        try:
            poll_count += 1
            now = int(time.time())

            # 全量解密限速：每10秒一次，从原始加密文件完整解密
            # （不用 decrypt_wal 增量补丁，避免对已解密页面重复解密导致损坏）
            if now - last_decrypt_time >= 10:
                for db_name in [f'msg_{i}' for i in range(10)]:
                    db_path = os.path.join(config.WAL_BASE, f'{db_name}.db')
                    wal_path = os.path.join(config.WAL_BASE, f'{db_name}.db-wal')
                    key_name = f'Message/{db_name}.db'
                    if os.path.exists(db_path) and os.path.getsize(db_path) > 32:
                        enc_key = bytes.fromhex(keys[key_name]['enc_key'])
                        out_path = os.path.join(config.DECRYPTED_DIR, 'Message', f'{db_name}.db')
                        tmp_path = out_path + '.tmp_full'
                        try:
                            # 1. 解密主数据库
                            full_decrypt(db_path, tmp_path, enc_key)
                            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 32:
                                os.replace(tmp_path, out_path)
                            # 2. 解密 WAL 并追加到解密后的数据库
                            if os.path.exists(wal_path) and os.path.getsize(wal_path) > 32:
                                decrypt_wal(wal_path, out_path, enc_key)
                        except Exception as e:
                            log(f"[DECRYPT ERROR] {db_name}: {e}")
                last_decrypt_time = now

            # 遍历数据库
            msg_dir = os.path.join(config.DECRYPTED_DIR, 'Message')
            for db_path in sorted(glob.glob(os.path.join(msg_dir, 'msg_*.db'))):
                try:
                    conn = sqlite3.connect(db_path, timeout=1)
                    c = conn.cursor()
                    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'Chat_*' AND name NOT GLOB '*_dels'")
                    tables = [r[0] for r in c.fetchall()]
                    for table in tables:
                        try:
                            c.execute(f'SELECT msgContent, msgCreateTime, mesDes, mesLocalID, ConBlob FROM "{table}" WHERE messageType = 1 AND mesDes = 1 ORDER BY msgCreateTime DESC LIMIT 10')
                            for row in c.fetchall():
                                try:
                                    if not row[0] or str(row[0]).startswith('<'):
                                        continue
                                    content_str = str(row[0])
                                    ctime = row[1]
                                    mes_local_id = row[3]
                                    blob = row[4]
                                except:
                                    continue
                                # 用 mesLocalID 精准去重
                                if mes_local_id in processed_ids:
                                    continue
                                # ⭐ 只处理20分钟内的消息（不许删除，2026-04-03）
                                if now - ctime > 20 * 60:
                                    continue
                                processed_ids.add(mes_local_id)
                                save_processed_throttled()

                                is_group = is_group_message(blob)
                                is_at = is_at_me(content_str) if is_group else False
                                sender = "未知"
                                sender_wxid = None
                                actual_content = content_str

                                if is_group:
                                    m = re.match(r'^([^:\n]+)[:\n](.*)', content_str, re.DOTALL)
                                    if m:
                                        sender = m.group(1)
                                        actual_content = m.group(2).strip()
                                else:
                                    wxid_from_blob, nickname_from_blob = extract_sender_from_blob(blob)
                                    if wxid_from_blob:
                                        sender = nickname_from_blob
                                        sender_wxid = wxid_from_blob

                                if sender != "未知" and len(actual_content) > 0:
                                    wxid_clean, nickname_clean = clean_sender(sender)
                                    ts = time.strftime('%m-%d %H:%M', time.localtime(ctime))
                                    log(f"📩 [{ts}] {nickname_clean}: {actual_content[:30]}... (群:{is_group}, @:{is_at})")
                                    msg_queue.put({
                                        'sender': nickname_clean,
                                        'content': actual_content[:100],
                                        'is_group': is_group,
                                        'is_at': is_at,
                                        'sender_wxid': sender_wxid if sender_wxid else wxid_clean,
                                        'ctime': ctime,
                                        'mes_local_id': mes_local_id
                                    })
                                    last_message_time = now
                                    wechat_activated = True
                        except Exception as e:
                            log(f"[ERROR] 消息处理错误: {e}")
                    conn.close()
                except Exception as e:
                    log(f"查询错误: {e}")
            if poll_count % 30 == 0:
                save_processed(processed_ids)
        except Exception as e:
            log(f"轮询错误: {e}")
        time.sleep(0.3)


# ====== 线程2：AI 处理 ======
def process_messages():
    global RUNNING, user_pending, pending_lock
    log("AI处理线程开始运行")
    while True:
        try:
            msg = msg_queue.get(timeout=5)
            log(f"📥 收到消息队列: {msg.get('sender', '?')} - {msg.get('content', '')[:20]}")
            sender = msg['sender']
            content = msg['content']
            is_group = msg['is_group']
            is_at = msg['is_at']
            sender_wxid = msg['sender_wxid']

            # 跳过自己发的消息
            if sender_wxid == config.MY_WXID:
                msg_queue.task_done()
                continue

            # 群聊跳过（只处理私聊）
            if is_group:
                msg_queue.task_done()
                continue

            # 人格切换命令
            if content.startswith('!人格 ') or content.startswith('!切换 '):
                target = content.split(' ', 1)[1].strip()
                if set_persona(target):
                    persona, _ = get_current_persona()
                    log(f"✅ 人格切换为: {persona['name']}")
                    send_reply_to_contact(sender, f"已切换为：{persona['name']}", sender_wxid, is_group)
                else:
                    available = [f"{n}({i})" for i, n in list_personas()]
                    send_reply_to_contact(sender, f"未知人格，可用：{' / '.join(available)}", sender_wxid, is_group)
                msg_queue.task_done()
                continue
            if content.strip() == '!人格':
                persona, _ = get_current_persona()
                available = [n for _, n in list_personas()]
                send_reply_to_contact(sender, f"当前：{persona['name']}，可选：{' / '.join(available)}", sender_wxid, is_group)
                msg_queue.task_done()
                continue

            # 消息合并：5秒内同用户连续消息合并，等待窗口到期后统一回复
            now = time.time()
            wxid_key = sender_wxid if sender_wxid else f"nick_{sender}"
            mes_local_id = msg.get('mes_local_id')

            with processing_lock:
                if wxid_key in user_pending:
                    old = user_pending[wxid_key]
                    user_pending[wxid_key] = {
                        'messages': old['messages'] + [content],
                        'last_time': now,
                        'pending': True,  # pending=True 表示等待合并窗口
                        'mes_local_id': mes_local_id,
                        'is_group': is_group,
                        'is_at': is_at,
                        'sender_wxid': sender_wxid,
                        'sender': sender
                    }
                    log(f"📦 合并消息: {sender} - {[m[:15] for m in user_pending[wxid_key]['messages']]}")
                    msg_queue.task_done()
                    continue

                # 全新用户，启动合并窗口
                user_pending[wxid_key] = {
                    'messages': [content], 'last_time': now, 'pending': True,
                    'mes_local_id': mes_local_id, 'is_group': is_group,
                    'is_at': is_at, 'sender_wxid': sender_wxid, 'sender': sender
                }
                log(f"📦 启动合并窗口: {sender} - {[content[:15]]}")
                msg_queue.task_done()
        except Empty:
            pass
        except Exception as e:
            log(f"[ERROR] process_messages异常: {e}")
            import traceback
            traceback.print_exc()


# ====== 线程3：发送回复 ======
_send_dedup = {}  # {mes_local_id: timestamp}
_send_dedup_lock = threading.Lock()

def send_replies():
    global RUNNING
    while True:
        # 定期清理过期的发送去重记录
        now = int(time.time())
        with _send_dedup_lock:
            for k in list(_send_dedup.keys()):
                if now - _send_dedup[k] >= 60:
                    del _send_dedup[k]

        try:
            item = reply_queue.get(timeout=5)
            sender = item['sender']
            reply = item['reply']
            sender_wxid = item['sender_wxid']
            mes_local_id = item.get('mes_local_id')

            # 发送去重：同一 mes_local_id 60秒内只发送一次
            if mes_local_id:
                now = time.time()
                with _send_dedup_lock:
                    if mes_local_id in _send_dedup and now - _send_dedup[mes_local_id] < 60:
                        log(f"⏭️ 发送去重，跳过 mes_local_id={mes_local_id}")
                        reply_queue.task_done()
                        continue
                    _send_dedup[mes_local_id] = now

            if send_reply_to_contact(sender, reply, sender_wxid, item.get('is_group', False)):
                log("发送成功")
                add_to_context(sender, sender, reply)
            else:
                log("发送失败")
            reply_queue.task_done()
        except Empty:
            pass
        except Exception as e:
            log(f"[ERROR] send_replies异常: {e}")
            import traceback
            traceback.print_exc()


# ====== 合并检查：窗口到期后触发AI回复 ======
def check_pending_messages():
    global user_pending, pending_lock, RUNNING
    while True:
        try:
            time.sleep(1)
            if not RUNNING:
                continue
            now = time.time()
            with pending_lock:
                for wxid_key, data in list(user_pending.items()):
                    if data.get('pending') and now - data['last_time'] >= config.MERGE_WINDOW:
                        merged = " ".join(data['messages'])
                        sender = data.get('sender', wxid_key)
                        sender_wxid = data.get('sender_wxid')
                        is_group = data.get('is_group', False)
                        is_at = data.get('is_at', False)
                        mes_local_id = data.get('mes_local_id')
                        old_count = len(data['messages'])
                        # 标记：AI正在处理，防止队列里重复触发
                        user_pending[wxid_key]['pending'] = False
                        user_pending[wxid_key]['messages'] = []

                        # 锁外调用AI
                        if merged:
                            log(f"⏰ 合并窗口到期 [{old_count}条]，触发AI回复: {merged[:30]}...")
                            _do_ai_reply(sender, merged, is_group, is_at, sender_wxid, mes_local_id)

                        # AI回复后，继续等待新消息（有就继续合并）
                        if wxid_key in user_pending:
                            if user_pending[wxid_key]['messages']:
                                user_pending[wxid_key]['pending'] = True
                            else:
                                del user_pending[wxid_key]

        except Exception as e:
            log(f"合并检查错误: {e}")


def _do_ai_reply(sender, content, is_group, is_at, sender_wxid, mes_local_id=None):
    if not RUNNING:
        return

    log(f"⚙️ AI处理中: {sender} - {content[:30]}...")
    context = get_context_for_wxid(sender)
    reply = ai_reply(sender, content, context)
    if not reply:
        log("❌ AI回复失败")
        return

    # 群聊回复开头@对方
    if is_group:
        reply = f"@{sender} {reply}"

    # 去重：用 mesLocalID 精准去重，30秒内同一消息不重复回复
    if mes_local_id:
        now = time.time()
        with _recent_lock:
            if mes_local_id in _recent_reply_keys and now - _recent_reply_keys[mes_local_id] < 30:
                log(f"⏭️ 重复回复，跳过 mes_local_id={mes_local_id}")
                return
            _recent_reply_keys[mes_local_id] = now
            for k in list(_recent_reply_keys.keys()):
                if now - _recent_reply_keys[k] >= 30:
                    del _recent_reply_keys[k]

    log(f"✅ AI回复生成: {reply}")
    reply_queue.put({'sender': sender, 'reply': reply, 'sender_wxid': sender_wxid, 'mes_local_id': mes_local_id, 'is_group': is_group})
