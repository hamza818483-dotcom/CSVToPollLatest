#!/usr/bin/env python3
# ============================================================
#  atlas_bot.py  —  Atlas Bot for Render.com
# ============================================================

import os, sys, io, csv, asyncio, logging, json, re, pickle
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ============================================================
#  ⚙️  CONFIG
# ============================================================
BOT_TOKEN = "8757116951:AAGwrlY7ILI-i6-9tmzICjJI3mw6dk75xM0"
OWNER_ID  = 5341425626

ADMINS_FILE  = "data/admins.txt"

POLL_DELAY_SEC    = 2
POLL_IS_ANONYMOUS = True
POLL_TYPE         = "quiz"
MAX_RETRY         = 5
RETRY_DELAY       = 3

DEFAULT_MARKER_BEFORE = ""
DEFAULT_MARKER_AFTER  = ""
DEFAULT_EXP_PREFIX    = ""

# ============================================================
#  PERSISTENT STORAGE
# ============================================================
STORE_FILE  = "data/file_store.pkl"
MARKER_FILE = "data/markers.pkl"

def save_all():
    try:
        os.makedirs("data", exist_ok=True)
        with open(STORE_FILE, "wb") as f:
            pickle.dump(_FILE_STORE, f)
        with open(MARKER_FILE, "wb") as f:
            pickle.dump({
                "marker_before": _MARKER_BEFORE,
                "marker_after": _MARKER_AFTER,
                "exp_prefix": _EXP_PREFIX
            }, f)
    except Exception as e:
        logger.error(f"Save error: {e}")

def load_all():
    global _FILE_STORE, _MARKER_BEFORE, _MARKER_AFTER, _EXP_PREFIX
    try:
        if os.path.exists(STORE_FILE):
            with open(STORE_FILE, "rb") as f:
                _FILE_STORE = pickle.load(f)
    except:
        pass
    try:
        if os.path.exists(MARKER_FILE):
            with open(MARKER_FILE, "rb") as f:
                data = pickle.load(f)
                _MARKER_BEFORE = data.get("marker_before", {})
                _MARKER_AFTER = data.get("marker_after", {})
                _EXP_PREFIX = data.get("exp_prefix", {})
    except:
        pass

# ============================================================
#  POLL PAUSE/RESUME STATE
# ============================================================
_POLL_PAUSED: dict = {}

# ============================================================
#  LOGGING
# ============================================================
os.makedirs("data", exist_ok=True)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
#  CSV HELPER
# ============================================================
OPTION_LABELS = ["A", "B", "C", "D", "E"]

def parse_csv_bytes(data: bytes):
    text   = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows   = list(reader)
    return rows, list(reader.fieldnames or [])

def get_options(row: dict):
    opts = []
    for i in range(1, 6):
        for key in [f"option{i}", f"option({i})", f"option_{i}", f"opt{i}", 
                    f"Option{i}", f"OPTION{i}"]:
            val = row.get(key, "").strip()
            if val:
                opts.append(val)
                break
    return opts

def get_answer_label(row: dict, opts: list):
    for key in ["answer", "Answer", "ANSWER", "correct_answer", "correct_answer", "correct"]:
        ans_val = row.get(key, "").strip()
        if ans_val:
            for i, opt in enumerate(opts):
                if ans_val.lower() == opt.lower():
                    return OPTION_LABELS[i], opt
            if ans_val.upper() in OPTION_LABELS:
                idx = OPTION_LABELS.index(ans_val.upper())
                if idx < len(opts):
                    return ans_val.upper(), opts[idx]
            try:
                idx = int(ans_val) - 1
                if 0 <= idx < len(opts):
                    return OPTION_LABELS[idx], opts[idx]
            except:
                pass
    return "A", (opts[0] if opts else "?")

def _apply_marker_to_question(question: str, marker_before: str, marker_after: str) -> str:
    parts = []
    if marker_before:
        parts.append(marker_before)
        parts.append("")
    parts.append(question)
    if marker_after:
        parts.append("")
        parts.append(marker_after)
    return "\n".join(parts)

def _apply_exp_prefix(exp: str, prefix: str) -> str:
    if prefix and exp:
        return f"{exp}\n\n{prefix}"
    elif prefix and not exp:
        return prefix
    return exp

# ============================================================
#  ADMIN HANDLER
# ============================================================
_ADMINS: set = set()

def load_admins():
    global _ADMINS
    _ADMINS = {OWNER_ID}
    if os.path.exists(ADMINS_FILE):
        with open(ADMINS_FILE) as f:
            for line in f:
                try:
                    _ADMINS.add(int(line.strip()))
                except Exception:
                    pass

def save_admins():
    os.makedirs(os.path.dirname(ADMINS_FILE), exist_ok=True)
    with open(ADMINS_FILE, "w") as f:
        for uid in _ADMINS:
            if uid != OWNER_ID:
                f.write(f"{uid}\n")

def is_admin(user_id: int):
    return user_id in _ADMINS

# ============================================================
#  MARKER / EXP PRESET
# ============================================================
_MARKER_BEFORE: dict = {}
_MARKER_AFTER:  dict = {}
_EXP_PREFIX:    dict = {}

async def cmd_marker(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ অ্যাডমিন পারমিশন নেই।"); return
    text = " ".join(ctx.args).strip()
    _MARKER_BEFORE[uid] = text
    save_all()
    if text:
        await update.message.reply_text(f"✅ MCQ এর উপরে marker:\n`{text}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("✅ MCQ এর উপরের marker সরানো হয়েছে।")

async def cmd_marker_aft(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ অ্যাডমিন পারমিশন নেই।"); return
    text = " ".join(ctx.args).strip()
    _MARKER_AFTER[uid] = text
    save_all()
    if text:
        await update.message.reply_text(f"✅ MCQ এর নিচে marker:\n`{text}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("✅ MCQ এর নিচের marker সরানো হয়েছে।")

async def cmd_exp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ অ্যাডমিন পারমিশন নেই।"); return
    text = " ".join(ctx.args).strip()
    _EXP_PREFIX[uid] = text
    save_all()
    if text:
        await update.message.reply_text(f"✅ ব্যাখ্যার পরে যোগ হবে:\n`{text}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("✅ ব্যাখ্যার prefix সরানো হয়েছে।")

# ============================================================
#  /pause & /resume
# ============================================================
async def cmd_pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    _POLL_PAUSED[uid] = True
    await update.message.reply_text("⏸️ পোল থামানো হয়েছে!\n▶️ `/resume` দিয়ে আবার চালু করো।", parse_mode="Markdown")

async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    _POLL_PAUSED[uid] = False
    await update.message.reply_text("▶️ পোল আবার চলছে!")

# ============================================================
#  ADMIN COMMANDS
# ============================================================
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Atlas Bot এ স্বাগতম!*\n\n"
        "📌 *সব কমান্ড:*\n\n"
        "🔴 *Poll টুলস*\n"
        "`/csv` — CSV/JSON থেকে Poll\n"
        "`/csvS <কতটা> <চ্যানেল> <Topic>` — সিরিয়াল Poll\n\n"
        "⏯️ *Control*\n"
        "`/pause` — পোল থামাও\n"
        "`/resume` — পোল চালু\n"
        "`/restart` — বট রিস্টার্ট\n\n"
        "🟡 *Poll সেটিংস*\n"
        "`/marker <text>` — প্রশ্নের উপরে marker (1 line gap)\n"
        "`/markerAft <text>` — প্রশ্নের নিচে marker (1 line gap)\n"
        "`/exp <text>` — ব্যাখ্যার পরে text\n\n"
        "🔵 *ফাইল*\n"
        "`/split <number>` — ফাইল ভাগ (সরাসরি)\n"
        "`/convert` — CSV → JSON\n"
        "`/rename <নতুন নাম>` — Rename + রিটার্ন\n\n"
        "🟢 *অ্যাডমিন*\n"
        "`/permit <user_id>` — অ্যাডমিন\n"
        "`/addchannel <id> <নাম>` — চ্যানেল যোগ\n\n"
        "📎 CSV/JSON ফাইল পাঠাও → কমান্ড দাও"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_permit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ শুধু Owner।"); return
    if not ctx.args:
        await update.message.reply_text("`/permit <user_id>`"); return
    try:
        uid = int(ctx.args[0])
        _ADMINS.add(uid)
        save_admins()
        await update.message.reply_text(f"✅ `{uid}` অ্যাডমিন করা হয়েছে।")
    except ValueError:
        await update.message.reply_text("❌ সঠিক User ID দাও।")

async def cmd_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    save_all()
    await update.message.reply_text("🔄 রিস্টার্ট হচ্ছে...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# ============================================================
#  FILE STORE
# ============================================================
_FILE_STORE: dict = {}

def store_file(user_id: int, data: bytes, filename: str, file_type: str = "csv"):
    _FILE_STORE[user_id] = {
        "data": data, 
        "filename": filename,
        "type": file_type
    }
    save_all()

def get_file(user_id: int):
    return _FILE_STORE.get(user_id)

def _get_rows_from_stored(stored: dict):
    if stored["type"] == "json":
        json_data = json.loads(stored["data"].decode("utf-8"))
        rows = []
        for item in json_data:
            opts = item.get("options", {})
            row = {
                "questions": item.get("question", ""),
                "option1": opts.get("A", ""),
                "option2": opts.get("B", ""),
                "option3": opts.get("C", ""),
                "option4": opts.get("D", ""),
                "answer": item.get("correct_answer", "A"),
                "explanation": item.get("explanation", "")
            }
            rows.append(row)
        return rows
    else:
        rows, _ = parse_csv_bytes(stored["data"])
        return rows

# ============================================================
#  /rename
# ============================================================
async def cmd_rename(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    stored = get_file(uid)
    if not stored:
        await update.message.reply_text("📎 আগে একটি ফাইল পাঠাও।"); return
    if not ctx.args:
        await update.message.reply_text("`/rename <নতুন নাম>`"); return
    
    new_name = " ".join(ctx.args).strip()
    old_suffix = Path(stored["filename"]).suffix
    if not new_name.endswith((".csv", ".json")):
        new_name += old_suffix
    
    await update.message.reply_document(
        document=io.BytesIO(stored["data"]),
        filename=new_name,
        caption=f"✅ Renamed: `{stored['filename']}` → `{new_name}`",
        parse_mode="Markdown"
    )
    
    _FILE_STORE[uid]["filename"] = new_name
    save_all()

# ============================================================
#  /convert — CSV → JSON
# ============================================================
async def cmd_convert(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    stored = get_file(uid)
    if not stored or stored["type"] != "csv":
        await update.message.reply_text("📎 আগে একটি CSV ফাইল পাঠাও।"); return
    
    rows, headers = parse_csv_bytes(stored["data"])
    
    json_data = []
    for idx, row in enumerate(rows, 1):
        opts = get_options(row)
        ans_label, _ = get_answer_label(row, opts)
        exp = row.get("explanation", "").strip()
        
        question_obj = {
            "question_number": str(idx),
            "question": row.get("questions", "").strip(),
            "options": {
                "A": opts[0] if len(opts) > 0 else "",
                "B": opts[1] if len(opts) > 1 else "",
                "C": opts[2] if len(opts) > 2 else "",
                "D": opts[3] if len(opts) > 3 else ""
            },
            "correct_answer": ans_label,
            "explanation": exp
        }
        json_data.append(question_obj)
    
    json_bytes = json.dumps(json_data, ensure_ascii=False, indent=2).encode("utf-8")
    json_name  = stored["filename"].replace(".csv", ".json")
    
    store_file(uid, json_bytes, json_name, "json")
    
    await update.message.reply_document(
        document=io.BytesIO(json_bytes),
        filename=json_name,
        caption=f"✅ JSON কনভার্ট!\n📊 প্রশ্ন: {len(rows)}টি"
    )

# ============================================================
#  /split — সরাসরি ফাইল
# ============================================================
async def cmd_split(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    stored = get_file(uid)
    if not stored:
        await update.message.reply_text("📎 আগে একটি ফাইল পাঠাও。"); return
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("`/split 20`"); return

    n = int(ctx.args[0])
    
    if stored["type"] == "json":
        json_data = json.loads(stored["data"].decode("utf-8"))
        rows = json_data
        headers = ["question_number", "question", "options", "correct_answer", "explanation"]
    else:
        rows, headers = parse_csv_bytes(stored["data"])
    
    if not rows:
        await update.message.reply_text("❌ ফাইলে কোনো তথ্য নেই。"); return

    total_parts = (len(rows) + n - 1) // n
    base_name = stored["filename"].replace(".csv", "").replace(".json", "")
    ext = ".json" if stored["type"] == "json" else ".csv"
    
    msg = await update.message.reply_text(f"⏳ {len(rows)}টি → {total_parts}টি ফাইল...")

    for i in range(total_parts):
        chunk = rows[i*n : (i+1)*n]
        part_name = f"{base_name}_part{i+1:02d}{ext}"
        
        if stored["type"] == "json":
            chunk_bytes = json.dumps(chunk, ensure_ascii=False, indent=2).encode("utf-8")
        else:
            csv_buf = io.StringIO()
            writer = csv.DictWriter(csv_buf, fieldnames=headers)
            writer.writeheader()
            writer.writerows(chunk)
            chunk_bytes = csv_buf.getvalue().encode("utf-8-sig")
        
        await update.message.reply_document(
            document=chunk_bytes,
            filename=part_name,
            caption=f"📄 {part_name} | 📊 {len(chunk)}টি"
        )
        await asyncio.sleep(1)

    await msg.delete()
    await update.message.reply_text(
        f"✅ সম্পন্ন!\n📊 মোট: {len(rows)} | 📁 ভাগ: {total_parts} | 📝 প্রতি: {n}টি"
    )

# ============================================================
#  FILE HANDLER
# ============================================================
async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    doc = update.message.document
    if not doc: return
    fname = doc.file_name or ""

    if fname.lower().endswith((".csv", ".json")):
        msg = await update.message.reply_text("⏳ ফাইল লোড হচ্ছে...")
        try:
            file_obj = await ctx.bot.get_file(doc.file_id)
            buf = io.BytesIO()
            await file_obj.download_to_memory(buf)
            data = buf.getvalue()
            
            if fname.lower().endswith(".csv"):
                rows, headers = parse_csv_bytes(data)
                required = {"questions", "answer"}
                headers_lower = [h.lower() for h in headers]
                missing = required - set(headers_lower)
                if missing:
                    await msg.edit_text(f"⚠️ কলাম নেই: `{'`, `'.join(missing)}`\nপাওয়া: `{'`, `'.join(headers)}`")
                    return
                store_file(uid, data, fname, "csv")
            else:
                json_data = json.loads(data.decode("utf-8"))
                rows = json_data
                store_file(uid, data, fname, "json")
            
            await msg.edit_text(
                f"✅ ফাইল লোড!\n📊 প্রশ্ন: {len(rows)}টি\n\n"
                f"🔹 `/split N` | `/csv` | `/csvS N name Topic`\n"
                f"🔹 `/convert` | `/rename name`"
            )
        except Exception as e:
            logger.error(f"File load error: {e}")
            await msg.edit_text(f"❌ সমস্যা: {e}")

# ============================================================
#  POLL LINK HELPER
# ============================================================
async def _get_message_link(bot, chat_id: int, message_id: int) -> str:
    try:
        chat_info = await bot.get_chat(chat_id)
        if chat_info.username:
            return f"https://t.me/{chat_info.username}/{message_id}"
        else:
            chat_id_str = str(chat_id).replace("-100", "")
            return f"https://t.me/c/{chat_id_str}/{message_id}"
    except Exception:
        return ""

# ============================================================
#  POLL SENDER (with retry + pause)
# ============================================================
async def _send_poll_with_retry(bot, chat_id, question, options, correct_option_id, 
                                 explanation, reply_to_message_id, uid=None, max_retry=MAX_RETRY):
    for attempt in range(1, max_retry + 1):
        while _POLL_PAUSED.get(uid, False):
            await asyncio.sleep(2)
        
        try:
            sent = await bot.send_poll(
                chat_id=chat_id,
                question=question,
                options=options,
                type=POLL_TYPE,
                correct_option_id=correct_option_id,
                explanation=explanation,
                is_anonymous=POLL_IS_ANONYMOUS,
                reply_to_message_id=reply_to_message_id,
            )
            return sent, True
        except Exception as e:
            if attempt < max_retry:
                logger.warning(f"Poll attempt {attempt} failed: {e}. Retrying...")
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error(f"Poll FAILED after {max_retry} attempts: {e}")
                return None, False
    return None, False

# ============================================================
#  /csv — Poll পাঠানো
# ============================================================
_POLL_SESSION: dict = {}

async def cmd_csv_poll(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    stored = get_file(uid)
    if not stored:
        await update.message.reply_text("📎 আগে CSV/JSON ফাইল পাঠাও।"); return

    pre_msg = " ".join(ctx.args) if ctx.args else ""
    rows = _get_rows_from_stored(stored)
    
    if not rows:
        await update.message.reply_text("❌ ফাইলে কোনো প্রশ্ন নেই।"); return

    _POLL_SESSION[uid] = {
        "rows": rows,
        "pre_msg": pre_msg,
        "total_rows": len(rows),
        "topic": stored["filename"].replace(".csv","").replace(".json",""),
        "marker_before": _MARKER_BEFORE.get(uid, DEFAULT_MARKER_BEFORE),
        "marker_after": _MARKER_AFTER.get(uid, DEFAULT_MARKER_AFTER),
        "exp_prefix": _EXP_PREFIX.get(uid, DEFAULT_EXP_PREFIX),
    }

    keyboard = await _build_channel_keyboard(ctx.bot, uid)
    if not keyboard:
        await update.message.reply_text("❌ কোনো চ্যানেল নেই। `/addchannel -100xxx নাম` দাও।"); return

    await update.message.reply_text(
        f"📡 *{len(rows)}টি* প্রশ্ন পাওয়া গেছে।\n\n*কোন চ্যানেলে পাঠাবো?*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============================================================
#  /csvS — সিরিয়াল Batch Poll
# ============================================================
async def cmd_csvS(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    stored = get_file(uid)
    if not stored:
        await update.message.reply_text("📎 আগে ফাইল পাঠাও।"); return

    if len(ctx.args) < 3:
        await update.message.reply_text(
            "`/csvS <কতটা> <চ্যানেল নাম> <Topic>`\n"
            "উদাহরণ: `/csvS 10 chemistry রসায়ন অধ্যায়-১`",
            parse_mode="Markdown"
        ); return

    try:
        batch_size = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ প্রথম আর্গুমেন্ট সংখ্যা হতে হবে。"); return

    ch_name = ctx.args[1].lower()
    topic = " ".join(ctx.args[2:])
    
    rows = _get_rows_from_stored(stored)
    if not rows:
        await update.message.reply_text("❌ ফাইলে কোনো প্রশ্ন নেই。"); return

    matching_channels = await _find_channels_by_name(ctx.bot, ch_name)
    
    if not matching_channels:
        await update.message.reply_text(f"❌ '{ctx.args[1]}' চ্যানেল পাওয়া যায়নি।"); return
    
    if len(matching_channels) == 1:
        ch_id = matching_channels[0]["id"]
        ch_display = matching_channels[0]["name"]
        await _start_csvS_poll(update, ctx, uid, batch_size, ch_id, topic, rows, ch_display)
    else:
        _POLL_SESSION[uid] = {
            "rows": rows, "batch_size": batch_size, "topic": topic, "csvS_mode": True,
            "marker_before": _MARKER_BEFORE.get(uid, DEFAULT_MARKER_BEFORE),
            "marker_after": _MARKER_AFTER.get(uid, DEFAULT_MARKER_AFTER),
            "exp_prefix": _EXP_PREFIX.get(uid, DEFAULT_EXP_PREFIX),
        }
        
        keyboard = []
        for ch in matching_channels:
            keyboard.append([InlineKeyboardButton(
                f"📢 {ch['name']}", callback_data=f"csvS_ch_{ch['id']}_{uid}"
            )])
        
        await update.message.reply_text(
            f"🔍 '{ctx.args[1]}' নামে *{len(matching_channels)}টি* চ্যানেল পাওয়া গেছে।\nকোনটি?",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def _start_csvS_poll(update_or_query, ctx, uid, batch_size, ch_id, topic, rows, ch_display="Channel"):
    marker_before = _MARKER_BEFORE.get(uid, DEFAULT_MARKER_BEFORE)
    marker_after  = _MARKER_AFTER.get(uid, DEFAULT_MARKER_AFTER)
    exp_prefix    = _EXP_PREFIX.get(uid, DEFAULT_EXP_PREFIX)
    
    total_batches = (len(rows) + batch_size - 1) // batch_size
    
    if hasattr(update_or_query, 'message'):
        progress_msg = await update_or_query.message.reply_text(
            f"🚀 Serial Poll!\n📊 MCQ: {len(rows)}\n📦 ব্যাচ: {total_batches}\n📢 {ch_display}\n📌 {topic}"
        )
    else:
        progress_msg = await update_or_query.edit_message_text(
            f"🚀 Serial Poll!\n📊 MCQ: {len(rows)}\n📦 ব্যাচ: {total_batches}\n📢 {ch_display}\n📌 {topic}"
        )

    for b_idx in range(total_batches):
        batch = rows[b_idx * batch_size : (b_idx+1) * batch_size]
        part_n = b_idx + 1
        part_topic = f"{topic} By ATLAS\nPart-{part_n:02d}"

        sent_topic = await ctx.bot.send_message(ch_id, f"📌 {part_topic}")
        reply_to = sent_topic.message_id

        batch_first_msg_id = None
        batch_first_chat_id = None
        
        sent_count = 0
        errors = 0

        for row in batch:
            opts = get_options(row)
            if not opts or len(opts) < 2:
                errors += 1; continue
            opts = opts[:10]
            ans_label, _ = get_answer_label(row, opts)
            ans_idx = OPTION_LABELS.index(ans_label) if ans_label in OPTION_LABELS else 0
            
            q_text = row.get("questions", "?").strip()
            q_text = _apply_marker_to_question(q_text, marker_before, marker_after)
            q_text = q_text[:300]
            
            raw_exp = row.get("explanation", "").strip()
            if raw_exp:
                exp_text = _apply_exp_prefix(raw_exp, exp_prefix)[:200]
            elif exp_prefix:
                exp_text = exp_prefix[:200]
            else:
                exp_text = None
            
            sent, success = await _send_poll_with_retry(
                ctx.bot, ch_id, q_text, opts, ans_idx, exp_text, reply_to, uid
            )
            
            if success:
                if batch_first_msg_id is None:
                    batch_first_msg_id = sent.message_id
                    batch_first_chat_id = ch_id
                sent_count += 1
            else:
                errors += 1
            
            await asyncio.sleep(POLL_DELAY_SEC)

        batch_first_link = ""
        if batch_first_msg_id and batch_first_chat_id:
            batch_first_link = await _get_message_link(ctx.bot, batch_first_chat_id, batch_first_msg_id)
            if batch_first_link:
                batch_first_link = f"\n\n📍পোল যেখান থেকে শুরু হয়েছে:\n{batch_first_link}"

        finish_text = (
            f"🎉 ধন্যবাদ!\n"
            f"এটলাস আয়োজিত *{topic} (Part-{part_n:02d})* টপিকে পোল সলভে অংশগ্রহণ করার জন্য। 🙌\n\n"
            f"📊 মোট পোল: *{sent_count}টি*\n\n"
            f"তোমার স্কোর কত? 🤔\n( ? / {sent_count} )\n\nনিচে লিখো! 👇"
            + batch_first_link
        )
        await ctx.bot.send_message(ch_id, finish_text, parse_mode="Markdown",
                                   reply_to_message_id=reply_to)
        await asyncio.sleep(3)

    await progress_msg.edit_text(
        f"✅ Serial Poll শেষ!\n📤 মোট: {len(rows)} | 📦 ব্যাচ: {total_batches}"
    )

async def _find_channels_by_name(bot, name_lower: str) -> list:
    channels_file = "data/channels.txt"
    if not os.path.exists(channels_file): return []
    results = []
    with open(channels_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = line.split(None, 1)
            if len(parts) < 2: continue
            ch_id, ch_name = parts[0], parts[1]
            if name_lower in ch_name.lower():
                try:
                    ch_id_int = int(ch_id)
                    member = await bot.get_chat_member(ch_id_int, bot.id)
                    if member.status in ("administrator", "creator"):
                        results.append({"id": ch_id_int, "name": ch_name})
                except Exception:
                    pass
    return results

async def _build_channel_keyboard(bot, uid):
    channels_file = "data/channels.txt"
    if not os.path.exists(channels_file): return []
    keyboard = []
    with open(channels_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            try:
                parts = line.split(None, 1)
                ch_id = int(parts[0])
                ch_name = parts[1] if len(parts) > 1 else str(ch_id)
                member = await bot.get_chat_member(ch_id, bot.id)
                if member.status in ("administrator", "creator"):
                    keyboard.append([InlineKeyboardButton(
                        f"📢 {ch_name}", callback_data=f"poll_ch_{ch_id}_{uid}"
                    )])
            except Exception:
                pass
    return keyboard

# ============================================================
#  CALLBACK HANDLERS
# ============================================================
async def poll_channel_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    ch_id = int(parts[2])
    uid = int(parts[3])

    if query.from_user.id != uid:
        await query.answer("এটা তোমার সেশন না。", show_alert=True); return

    session = _POLL_SESSION.get(uid)
    if not session:
        await query.edit_message_text("❌ সেশন শেষ। আবার /csv দাও।"); return

    rows = session["rows"]; pre_msg = session["pre_msg"]; topic = session["topic"]
    marker_before = session.get("marker_before", "")
    marker_after = session.get("marker_after", "")
    exp_prefix = session.get("exp_prefix", "")

    await query.edit_message_text(f"🚀 {len(rows)}টি Poll পাঠানো হচ্ছে...\n📢 `{ch_id}`", parse_mode="Markdown")

    reply_to = None
    first_poll_msg_id = None
    first_poll_chat_id = None

    if pre_msg:
        pre_sent = await ctx.bot.send_message(ch_id, pre_msg)
        reply_to = pre_sent.message_id

    sent_count = 0; errors = 0
    for row in rows:
        opts = get_options(row)
        if not opts or len(opts) < 2:
            errors += 1; continue
        opts = opts[:10]
        ans_label, _ = get_answer_label(row, opts)
        ans_idx = OPTION_LABELS.index(ans_label) if ans_label in OPTION_LABELS else 0
        
        q_text = row.get("questions", "?").strip()
        q_text = _apply_marker_to_question(q_text, marker_before, marker_after)
        q_text = q_text[:300]
        
        raw_exp = row.get("explanation", "").strip()
        if raw_exp:
            exp_text = _apply_exp_prefix(raw_exp, exp_prefix)[:200]
        elif exp_prefix:
            exp_text = exp_prefix[:200]
        else:
            exp_text = None
        
        sent, success = await _send_poll_with_retry(
            ctx.bot, ch_id, q_text, opts, ans_idx, exp_text, reply_to, uid
        )
        
        if success:
            if first_poll_msg_id is None:
                first_poll_msg_id = sent.message_id
                first_poll_chat_id = ch_id
            sent_count += 1
        else:
            errors += 1
        
        await asyncio.sleep(POLL_DELAY_SEC)

    first_poll_link = ""
    if first_poll_msg_id and first_poll_chat_id:
        first_poll_link = await _get_message_link(ctx.bot, first_poll_chat_id, first_poll_msg_id)
        if first_poll_link:
            first_poll_link = f"\n\n📍পোল যেখান থেকে শুরু হয়েছে:\n{first_poll_link}"

    finish_text = (
        f"🎉 ধন্যবাদ!\n"
        f"এটলাস আয়োজিত *{topic}* টপিকে পোল সলভে অংশগ্রহণ করার জন্য। 🙌\n\n"
        f"📊 মোট পোল: *{sent_count}টি*\n\n"
        f"তোমার স্কোর কত? 🤔\n( ? / {sent_count} )\n\nনিচে লিখো! 👇"
        + first_poll_link
    )
    await ctx.bot.send_message(ch_id, finish_text, parse_mode="Markdown",
                               **({"reply_to_message_id": reply_to} if reply_to else {}))

    summary = f"✅ শেষ!\n📤 পাঠানো: {sent_count}টি\n"
    if errors: summary += f"⚠️ ব্যর্থ: {errors}টি\n"
    await query.edit_message_text(summary)

async def csvS_channel_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    ch_id = int(parts[2])
    uid = int(parts[3])

    if query.from_user.id != uid:
        await query.answer("এটা তোমার সেশন না。", show_alert=True); return

    session = _POLL_SESSION.get(uid)
    if not session or not session.get("csvS_mode"):
        await query.edit_message_text("❌ সেশন শেষ। আবার /csvS দাও।"); return

    await _start_csvS_poll(
        query, ctx, uid,
        session["batch_size"], ch_id, session["topic"],
        session["rows"], f"Channel {ch_id}"
    )

async def cmd_add_channel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(ctx.args) < 2:
        await update.message.reply_text("`/addchannel -100xxxxxxxxx নাম`"); return
    ch_id, ch_name = ctx.args[0], " ".join(ctx.args[1:])
    os.makedirs("data", exist_ok=True)
    with open("data/channels.txt", "a") as f:
        f.write(f"{ch_id} {ch_name}\n")
    await update.message.reply_text(f"✅ যোগ: {ch_name} ({ch_id})")

# ============================================================
#  MAIN
# ============================================================
def register_handlers(app: Application):
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("restart",    cmd_restart))
    app.add_handler(CommandHandler("pause",      cmd_pause))
    app.add_handler(CommandHandler("resume",     cmd_resume))
    app.add_handler(CommandHandler("permit",     cmd_permit))
    app.add_handler(CommandHandler("split",      cmd_split))
    app.add_handler(CommandHandler("csv",        cmd_csv_poll))
    app.add_handler(CommandHandler("csvS",       cmd_csvS))
    app.add_handler(CommandHandler("addchannel", cmd_add_channel))
    app.add_handler(CommandHandler("convert",    cmd_convert))
    app.add_handler(CommandHandler("rename",     cmd_rename))
    app.add_handler(CommandHandler("marker",     cmd_marker))
    app.add_handler(CommandHandler("markerAft",  cmd_marker_aft))
    app.add_handler(CommandHandler("exp",        cmd_exp))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(poll_channel_callback, pattern=r"^poll_ch_"))
    app.add_handler(CallbackQueryHandler(csvS_channel_callback, pattern=r"^csvS_ch_"))
    logger.info("✅ সব হ্যান্ডলার রেজিস্টার।")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    import traceback
    err = context.error
    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    logger.error(f"❌ Error:\n{tb}")

def main():
    logger.info("🚀 Atlas Bot শুরু...")
    load_admins()
    load_all()
    app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
    register_handlers(app)
    app.add_error_handler(error_handler)
    logger.info("✅ Bot চালু!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
