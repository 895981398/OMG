import os, json, time, subprocess, requests, threading, sqlite3, warnings, glob, sys, re, atexit, signal, random, traceback
import queue
from queue import Queue, Empty
from logging.handlers import RotatingFileHandler
import logging
import config

# 项目根目录（用于相对路径定位）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
warnings.filterwarnings('ignore')


# ====== 真人化回复函数 ======
def humanize_reply(reply, persona_id="zhang_chulan"):
    """
    对 AI 回复进行真人化处理，去掉 AI 感
    - 干掉空行、换行、多余空格
    - 短句控制（最多2句）
    - 按人格加口头禅
    """
    if not reply:
        return reply
    
    # 1. 干掉所有换行、空行、多余空格
    reply = reply.replace("\n", " ").replace("\r", "").replace("  ", " ").strip()
    
    # 2. 禁止一句话空格一句话（常见AI格式）
    reply = reply.replace("。 ", "。").replace("！ ", "！").replace("？ ", "？").replace(", ", ",")
    
    # 3. 短句严格控制：1-2句
    sentences = [s.strip() for s in reply.split("。") if s.strip()]
    if len(sentences) > 2:
        reply = "。".join(sentences[:2]) + "。"
    elif len(sentences) == 1:
        reply = sentences[0]
    else:
        reply = "。".join(sentences) + "。"
    
    # 4. 按人格加口头禅（40%概率）
    if random.random() < 0.4 and len(reply) > 5:
        if persona_id == "tong_jincheng":
            mantras = ["说实话", "知道吧", "没毛病吧", "别搞", "可以啊", "咱就是说"]
            reply = random.choice(mantras) + "，" + reply
        elif persona_id == "zhang_chulan":
            # 张楚岚风格偏冷淡，少加
            if random.random() < 0.2:
                reply = reply.replace("嗯", "嗯").replace("哦", "嗯")
    
    # 5. 防止过长（超过50字截断）
    if len(reply) > 50:
        reply = reply[:50]
    
    return reply
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
warnings.filterwarnings('ignore')


# ====== 全局状态 ======
RUNNING = True
last_message_time = 0
wechat_activated = False

# 消息队列
msg_queue = Queue(maxsize=100)
reply_queue = Queue(maxsize=100)

# 用户合并缓存（新架构）
user_messages = {}      # {wxid_key: [msg1, msg2, ...]} 合并窗口内的消息
user_lock = {}        # {wxid_key: threading.Lock()} 每用户独立锁

# 双状态控制
is_replying = {}      # {wxid_key: True} 是否正在回复中
last_reply = {}       # {wxid_key: timestamp} 上次回复时间（冷却用）
state_lock = threading.Lock()  # 保护 is_replying 和 last_reply

# 全局打断标志：被置为 True 时正在处理的 AI 调用立即停止
_interrupt_flag = False


# ====== 日志 ======
LOG_FILE = '/tmp/wechat_bot.log'

# 配置 RotatingFileHandler：10MB一个文件，保留5个
_logger = logging.getLogger('wechat_bot')
_logger.setLevel(logging.DEBUG)
_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
_handler.setLevel(logging.DEBUG)
_formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%m-%d %H:%M:%S')
_handler.setFormatter(_formatter)
_logger.addHandler(_handler)

def log(msg, level='info'):
    """分级日志：debug/info/warning/error"""
    print(f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}", flush=True)
    if level == 'debug':
        _logger.debug(msg)
    elif level == 'warning':
        _logger.warning(msg)
    elif level == 'error':
        _logger.error(msg)
    else:
        _logger.info(msg)

def log_error(msg):
    """错误日志，带异常信息"""
    print(f"[{time.strftime('%m-%d %H:%M:%S')}] ❌ {msg}", flush=True)
    _logger.error(msg)

def log_exception(msg):
    """异常日志，带完整堆栈"""
    tb = traceback.format_exc()
    print(f"[{time.strftime('%m-%d %H:%M:%S')}] ❌ {msg}", flush=True)
    print(f"   堆栈: {tb.replace(chr(10), ' | ')}", flush=True)
    _logger.error(f"{msg} | 堆栈: {tb}")


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

def add_to_context(wxid, sender_nickname, message, is_me=False):
    ctx = load_context()
    if wxid not in ctx:
        ctx[wxid] = {'nickname': sender_nickname, 'messages': [], 'last_update': time.time()}
    ctx[wxid]['messages'].append({'content': message, 'time': time.time(), 'is_me': is_me})
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
    
    # 加入最近对话上下文（最近5条，包含AI自己的回复）
    if context_messages:
        recent = context_messages[-5:] if len(context_messages) > 5 else context_messages
        history = []
        for m in recent:
            role = '你' if m.get('is_me') else '用户'
            history.append(f"{role}：{m['content']}")
        if history:
            prompt += f"\n\n【最近对话】\n" + "\n".join(history) + "\n"
    
    prompt += f"\n用户：{message}\n你："

    # 按优先级尝试所有模型
    for model in sorted(config.MODELS, key=lambda x: x['priority']):
        reply = call_model(model, prompt, persona_id)
        if reply:
            return reply
        log(f"⚠️ {model['name']} 失败，尝试下一个模型...")
    
    log("❌ 所有模型都失败了")
    return None


def call_model(model, prompt, persona_id):
    """统一调用模型"""
    api_key = model.get('api_key')
    if not api_key:
        return None
    
    for attempt in range(3):
        try:
            resp = requests.post(
                model['endpoint'],
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={
                    'model': model['model'],
                    'messages': [{'role': 'user', 'content': prompt}],
                    **config.API_PARAMS
                },
                timeout=model.get('timeout', 20)
            )
            result = resp.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            if content:
                log(f"✅ {model['name']} 回复成功")
                return humanize_reply(content, persona_id)
            
            # 检查特定错误码
            if model['name'] == 'minimax':
                if result.get('base_resp', {}).get('status_code') == 2064:
                    time.sleep(2 ** attempt)
        except Exception as e:
            log_exception(f"{model['name']} 调用失败")
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

            # 消息合并：新架构，线程安全
            now = time.time()
            wxid_key = sender_wxid if sender_wxid else f"nick_{sender}"

            # 获取或创建该用户的锁
            with state_lock:
                if wxid_key not in user_lock:
                    user_lock[wxid_key] = threading.Lock()
                lock = user_lock[wxid_key]

            with lock:
                if wxid_key in user_messages:
                    user_messages[wxid_key].append(content)
                    # 限制消息条数
                    if len(user_messages[wxid_key]) > config.MAX_MERGE_MESSAGES:
                        user_messages[wxid_key] = user_messages[wxid_key][-config.MAX_MERGE_MESSAGES:]
                    user_messages[wxid_key + '_last'] = now
                    log(f"📦 合并消息: {sender} - {[m[:15] for m in user_messages[wxid_key]]}")
                else:
                    user_messages[wxid_key] = [content]
                    user_messages[wxid_key + '_last'] = now
                    log(f"📦 启动合并窗口: {sender} - {[content[:15]]}")
            msg_queue.task_done()
        except Empty:
            pass
        except Exception as e:
            log_exception("process_messages 异常")


# ====== 线程3：发送回复 ======
def send_replies():
    global RUNNING
    while True:
        try:
            item = reply_queue.get(timeout=5)
            sender = item['sender']
            reply = item['reply']
            wxid_key = item.get('wxid_key', sender)
            is_group = item.get('is_group', False)
            sender_wxid = item.get('sender_wxid')

            if send_reply_to_contact(sender, reply, sender_wxid, is_group):
                log("发送成功")
                add_to_context(sender, sender, reply, is_me=True)
            else:
                log("发送失败")
            reply_queue.task_done()
        except Empty:
            pass
        except Exception as e:
            log_exception("send_replies 异常")


# ====== 合并检查：窗口到期后触发AI回复 ======
def check_pending_messages():
    global user_messages, is_replying, last_reply, state_lock, RUNNING
    while True:
        try:
            time.sleep(1)
            if not RUNNING:
                continue
            now = time.time()

            with state_lock:
                wxid_keys = list(user_messages.keys())

            for wxid_key in wxid_keys:
                if wxid_key.endswith('_last'):
                    continue

                last_time = user_messages.get(wxid_key + '_last', 0)
                if now - last_time < config.MERGE_WINDOW:
                    continue

                with state_lock:
                    if wxid_key not in user_messages:
                        continue
                    messages = user_messages.pop(wxid_key)
                    user_messages.pop(wxid_key + '_last', None)

                # 检查是否正在回复中
                with state_lock:
                    if wxid_key in is_replying and is_replying.get(wxid_key):
                        log(f"⏭️ {wxid_key} 正在回复中，跳过")
                        # 恢复消息，留到下一轮
                        user_messages[wxid_key] = messages
                        user_messages[wxid_key + '_last'] = now
                        continue

                # 检查冷却时间
                with state_lock:
                    last = last_reply.get(wxid_key, 0)
                    if now - last < config.COOLDOWN:
                        remaining = int(config.COOLDOWN - (now - last))
                        log(f"⏭️ {wxid_key} 冷却中，剩余{remaining}秒")
                        continue

                # 提取消息元数据（从队列消息里暂存，这里简化处理）
                merged = config.MSG_SEPARATOR.join(messages[-config.MAX_MERGE_MESSAGES:])
                sender = wxid_key if wxid_key.startswith('nick_') else wxid_key
                log(f"⏰ 合并窗口到期 [{len(messages)}条]，触发AI回复: {merged[:30]}...")

                # 调用AI（锁外执行）
                _do_ai_reply_safe(wxid_key, merged, sender)

        except Exception as e:
            log_exception("合并检查错误")


def _do_ai_reply_safe(wxid_key, merged, sender):
    """安全的AI回复调用，带锁保护和finally保证释放"""
    with state_lock:
        is_replying[wxid_key] = True

    try:
        context = get_context_for_wxid(wxid_key)
        reply = ai_reply(sender, merged, context)
        if not reply:
            log("❌ AI回复失败")
            return

        log(f"✅ AI回复生成: {reply}")
        # wxid_key 就是 sender_wxid（私聊时）
        reply_queue.put({'sender': sender, 'reply': reply, 'wxid_key': wxid_key, 'sender_wxid': wxid_key})

        # 成功才记录冷却时间
        with state_lock:
            last_reply[wxid_key] = time.time()

    except Exception as e:
        log_exception(f"_do_ai_reply AI调用异常")
    finally:
        # 无论如何都释放锁
        with state_lock:
            is_replying[wxid_key] = False


