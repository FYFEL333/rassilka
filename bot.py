import requests
import time
import re
import json
import os

TOKEN = "7700887302:AAGypG3ZEtWIn85j9SEFyJWDY207IOoSS-E"
API = f"https://api.telegram.org/bot{TOKEN}"
OWNER_ID = 6037202333
FOOTER = "[© SNX | SIGNAL NEXT – ПОДПИШИСЬ ☑️](https://t.me/+oah4P2-9oUcyM2Zi)"
CHATS_FILE = "chats.json"

last_message = {}
pending = {}
media_groups = {}
media_group_timers = {}

def load_chats():
    try:
        with open(CHATS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_chats(data):
    with open(CHATS_FILE, "w") as f:
        json.dump(data, f)

chats = load_chats()

def clean_text(text):
    if not text:
        return FOOTER
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        if re.search(r'https?://|t\.me|tg://|@', line, re.IGNORECASE):
            continue
        if any(kw in line.lower() for kw in [
            "подпис", "читай", "следи", "канал", "присоединяй",
            "узнай", "переходи", "тут", "больше на",
            "скачано из", "скачано через",
            "поделиться новостью", "поделись с другом"
        ]):
            continue
        clean_lines.append(line)
    cleaned = "\n".join(clean_lines).strip()
    return f"{cleaned}\n\n{FOOTER}"

def get_updates(offset=None):
    return requests.get(f"{API}/getUpdates", params={"timeout": 30, "offset": offset}).json()

def send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{API}/sendMessage", data=data)

def send_media_group(chat_id, media):
    return requests.post(f"{API}/sendMediaGroup", data={
        "chat_id": chat_id,
        "media": json.dumps(media),
        "parse_mode": "Markdown"
    })

def send_to_chat(cid, msg_list, final_text):
    photos, videos = [], []

    for msg in msg_list:
        if "photo" in msg:
            photos.append(msg["photo"][-1]["file_id"])
        elif "video" in msg:
            videos.append(msg["video"]["file_id"])

    total = photos + videos
    media_type = None
    if photos and not videos:
        media_type = "photo"
    elif videos and not photos:
        media_type = "video"

    if media_type:
        media = []
        for i, file_id in enumerate(total):
            media.append({
                "type": media_type,
                "media": file_id,
                "caption": final_text if i == 0 else "",
                "parse_mode": "Markdown"
            })
        r = send_media_group(cid, media)
        if r.status_code == 200:
            return

    for i, file_id in enumerate(total):
        kind = "photo" if file_id in photos else "video"
        data = {
            "chat_id": cid,
            kind: file_id,
            "parse_mode": "Markdown"
        }
        if i == 0:
            data["caption"] = final_text
        requests.post(f"{API}/send" + kind.capitalize(), data=data)

def handle_message(msg):
    user_id = msg["from"]["id"]
    chat_id = msg["chat"]["id"]
    chat_type = msg["chat"]["type"]
    text = msg.get("text")
    group_id = msg.get("media_group_id")

    if text and text.startswith("/admin") and user_id == OWNER_ID and chat_type == "private":
        markup = {
            "inline_keyboard": [[
                {"text": "💬 ДОБАВИТЬ ЧАТ 💬", "callback_data": "add_chat"}
            ]]
        }
        send_message(chat_id, "Панель управления:", reply_markup=markup)
        return

    if user_id in pending:
        if "/" not in text:
            send_message(chat_id, "Формат: НАЗВАНИЕ / АЙДИ\nПример: SNX ЧАТ / -1001234567890")
            return
        name, cid = map(str.strip, text.split("/", 1))
        chats[name] = cid
        save_chats(chats)
        del pending[user_id]
        send_message(chat_id, f"Чат «{name}» добавлен.")
        return

    
    if user_id == OWNER_ID and chat_type == "private":
        if group_id:
            if group_id not in media_groups:
                media_groups[group_id] = []
            media_groups[group_id].append(msg)
            media_group_timers[group_id] = time.time()
        else:
            if text and not text.startswith("/admin"):
                return  # Игнорируем все, кроме /admin
            last_message["single"] = [msg]
            show_buttons(chat_id)
def show_buttons(chat_id):
    buttons = [[{"text": name, "callback_data": f"to:{cid}"}] for name, cid in chats.items()]
    if chats:
        buttons.append([{"text": "⚡ ALL ⚡", "callback_data": "to:ALL"}])
    send_message(chat_id, "Куда отправить новость?", reply_markup={"inline_keyboard": buttons})

def handle_callback(query):
    data = query["data"]
    uid = query["from"]["id"]
    chat_id = query["message"]["chat"]["id"]
    qid = query["id"]
    requests.post(f"{API}/answerCallbackQuery", data={"callback_query_id": qid})

    if data == "add_chat":
        pending[uid] = True
        send_message(chat_id, "Введи:\nНАЗВАНИЕ / АЙДИ\nПример: SNX ЧАТ / -1001234567890")
        return

    if data.startswith("to:"):
        target = data.split(":", 1)[1]
        msg_list = None

        for gid, ts in list(media_group_timers.items()):
            if time.time() - ts >= 2:
                msg_list = media_groups[gid]
                del media_groups[gid]
                del media_group_timers[gid]
                break

        if not msg_list:
            msg_list = last_message.get("single")

        if not msg_list:
            send_message(chat_id, "Не удалось найти контент для отправки.")
            return

        text = ""
        for m in msg_list:
            if m.get("caption") or m.get("text"):
                text = m.get("caption") or m.get("text")
                break

        final = clean_text(text)
        targets = list(chats.values()) if target == "ALL" else [target]
        for cid in targets:
            send_to_chat(cid, msg_list, final)

        send_message(chat_id, "Новость отправлена.")

offset = None
print("SNX БОТ ЗАПУЩЕН...")

while True:
    try:
        updates = get_updates(offset)
        for upd in updates.get("result", []):
            offset = upd["update_id"] + 1
            if "message" in upd:
                handle_message(upd["message"])
            elif "callback_query" in upd:
                handle_callback(upd["callback_query"])

        for gid, ts in list(media_group_timers.items()):
            if time.time() - ts >= 2:
                msg_list = media_groups[gid]
                last_message["single"] = msg_list
                show_buttons(msg_list[0]["chat"]["id"])
                del media_groups[gid]
                del media_group_timers[gid]

    except Exception as e:
        print("Ошибка:", e)
        time.sleep(3)
