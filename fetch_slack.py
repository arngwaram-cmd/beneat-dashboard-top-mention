#!/usr/bin/env python3
"""
BeNeat Mention Dashboard — Slack Data Fetcher
=============================================
ดึง message จาก Hood & Pum ที่มีการ @mention คนอื่น
แล้ว update ค่า const RAW = [...] ใน index.html

ต้องการ:
  - env variable: SLACK_TOKEN  (Bot Token ที่มี scope search:read)
  - ไฟล์ index.html อยู่ใน directory เดียวกัน

วิธีรัน:
  SLACK_TOKEN=xoxb-xxx python fetch_slack.py
"""

import os
import re
import time
import requests
from datetime import datetime, timezone

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
SLACK_TOKEN = os.environ.get("SLACK_TOKEN", "")
HOOD_ID     = "U03E71FCC4F"
PUM_ID      = "U05MWPH3136"
MAX_PAGES   = 5          # 5 หน้า × 20 ข้อความ = 100 ข้อความต่อ sender
HTML_FILE   = "index.html"

# ─────────────────────────────────────────────
# USER ID → DISPLAY NAME (BeNeat style)
# ─────────────────────────────────────────────
USER_NAMES = {
    "U05NHE3AV3J": "Arngwara (Arng)",
    "U05MD71426T": "Nannaphat (Earn)",
    "U05MM8UJAVC": "Phonecha",
    "U05N8DE0GMS": "Thinnapon (Bacon)",
    "U09HLSRFMDM": "Pimvipa (Pim)",
    "U05N5SZ73EF": "Apitchaya (Rim)",
    "U05NVM2MPU0": "Nataphol (Nueng)",
    "U05N8DDGNTE": "Khomkhid (ต้น)",
    "U0767AW57L2": "Arissra (Jenny)",
    "U06J69N4P3L": "Napol (Arm)",
    "U07A0KVRCDD": "Peeraya (Bow)",
    "U06GMFJTQAF": "Vijai (Ton)",
    "U05NJK0FSGH": "Santi (Ti)",
    "U05MZAWRU5C": "Phataraphat (Dream)",
    "U05MRDXL30F": "Tharanarat (Dray)",
    "U09FAU86JFN": "Tarathorn (Spy)",
    "U0A218JEXDK": "Watcharapong (Pae)",
    "U05N60C3E90": "Nicha (Woonsen)",
    "U0802BVTRB8": "Siriprapa (Thip)",
    "U0ALK8ASKEF": "Supapich (แพรพีช)",
    "U09L4NM7W7M": "Piyawat (M)",
    "U05N5SY2L8K": "Moth",
    "U078CFARK7D": "Khotcharak (Wut)",
    "U0ADSRQQX7T": "Sutita (มิ้นท์)",
    "U05N22H9X28": "Tipawan (Nan)",
    "U06G6T4JL7R": "Thanapon (Mark)",
    "U0AHNCJHLVA": "Thitirat (มิน)",
    "U05N60C6VNW": "Jarinya (NumtaN)",
    "U05N5SZLLCT": "Nattarat (Nook)",
    "U05MDDC0ZN3": "Thepsuree (Pui)",
    "U05MTV6H5SN": "Pollawat (Joe)",
    "U03E71FCC4F": "Anon (Hood)",
    "U05MWPH3136": "Preeyalak (Pum)",
    # เพิ่ม member ใหม่ที่นี่:
    # "UXXXXXXXXX": "Name (Nickname)",
}

# ─────────────────────────────────────────────
# CHANNEL → TOPIC
# ─────────────────────────────────────────────
CHANNEL_TOPICS = [
    ("ceo_secretary",     "Notion / Knowledge"),
    ("dev_and_it",        "AI / Technology"),
    ("manager_and_super", "AI / Technology"),
    ("operation-team",    "Operations / BTaskee"),
    ("approval",          "Approval / Admin"),
    ("marketing",         "Marketing"),
    ("iso",               "ISO / Quality"),
    ("purchase",          "Approval / Admin"),
    ("qa_management",     "Approval / Admin"),
    ("cm_management",     "Operations / BTaskee"),
    ("mari_service",      "Marketing"),
    ("hq_beneat",         "Operations / BTaskee"),
]


def get_topic(channel_name: str) -> str:
    ch = channel_name.lower()
    for keyword, topic in CHANNEL_TOPICS:
        if keyword in ch:
            return topic
    return "General"


def extract_mentions(text: str, sender_id: str) -> list:
    """
    หา <@UXXX|display_name> ทุกอันใน message text
    - ตัดตัวเองออก (sender_id)
    - ตัด <!channel> / <!here> ออก (ไม่ใช่ specific mention)
    - คืนค่าเป็น list ของ display name (BeNeat style)
    """
    pattern = r"<@([A-Z0-9]+)(?:\|([^>]*))?>|<!(?:channel|here|everyone)>"
    matches = re.finditer(pattern, text)

    result = []
    seen = set()

    for m in matches:
        uid = m.group(1)
        if uid is None:
            continue  # <!channel> etc.
        if uid == sender_id:
            continue  # self-mention
        if uid in seen:
            continue
        seen.add(uid)

        # Look up known names first
        if uid in USER_NAMES:
            result.append(USER_NAMES[uid])
        else:
            # Fall back to the display name from the Slack message
            raw_name = m.group(2) or ""
            if raw_name:
                # "Firstname (Nick-ชื่อไทย)" → "Firstname (Nick)"
                clean = raw_name.split("(")[0].strip()
                if "(" in raw_name:
                    nick_part = raw_name.split("(")[1].rstrip(")")
                    # เอาแค่ส่วน English ก่อนตัวอักษรไทยหรือ dash
                    nick = re.split(r"[-\u0e00-\u0e7f]", nick_part)[0].strip()
                    result.append(f"{clean} ({nick})" if nick else clean)
                else:
                    result.append(clean)
            else:
                result.append(uid)  # last resort: raw ID

    return result


def clean_preview(text: str, max_len: int = 130) -> str:
    """ทำความสะอาด text ให้ใช้เป็น preview ได้"""
    text = re.sub(r"<@[A-Z0-9]+(?:\|[^>]+)?>", "", text)        # @mentions
    text = re.sub(r"<https?://[^>]+>", "", text)                  # URLs
    text = re.sub(r"<#[A-Z0-9]+(?:\|[^>]+)?>", "", text)          # #channels
    text = re.sub(r"<!(?:channel|here|everyone)>", "", text)       # <!channel>
    text = re.sub(r"[*_`~]", "", text)                             # markdown
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] if text else "(ไม่มีข้อความ)"


def ts_to_date(ts_str: str) -> str:
    """แปลง Slack timestamp → YYYY-MM-DD"""
    try:
        dt = datetime.fromtimestamp(float(ts_str), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return "2025-01-01"


def slack_search_page(query: str, page: int) -> dict:
    """เรียก Slack search.messages API"""
    url = "https://slack.com/api/search.messages"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    params = {
        "query": query,
        "sort": "timestamp",
        "sort_dir": "desc",
        "count": 20,
        "page": page,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_sender_mentions(sender_id: str, sender_label: str) -> list:
    """ดึง message จาก sender ที่มี @mention คนอื่น"""
    entries = []

    for page in range(1, MAX_PAGES + 1):
        print(f"  [page {page}] fetching {sender_label}...")
        try:
            data = slack_search_page(f"from:<@{sender_id}>", page)
        except Exception as e:
            print(f"  ERROR: {e}")
            break

        if not data.get("ok"):
            err = data.get("error", "unknown")
            print(f"  Slack API error: {err}")
            # ถ้า token ไม่มี scope search:read จะได้ error นี้
            if err in ("missing_scope", "not_authed", "invalid_auth"):
                print("  กรุณาตรวจสอบ SLACK_TOKEN และ scope search:read")
            break

        matches = data.get("messages", {}).get("matches", [])
        if not matches:
            print(f"  ไม่มี message เพิ่มเติมที่หน้า {page}")
            break

        for msg in matches:
            text = msg.get("text", "")

            # หา @mentions
            mentions = extract_mentions(text, sender_id)
            if not mentions:
                continue  # ข้าม message ที่ไม่ @mention ใคร

            # metadata
            channel      = msg.get("channel", {})
            channel_name = channel.get("name", "unknown")
            ts           = msg.get("ts", "0")
            date         = ts_to_date(ts)
            preview      = clean_preview(text)
            topic        = get_topic(channel_name)

            entries.append({
                "date":      date,
                "sender":    sender_label,
                "mentioned": mentions,
                "channel":   channel_name,
                "topic":     topic,
                "preview":   preview,
                "_ts":       float(ts),   # ใช้ sort, ไม่ export ไป JS
            })

        # Rate limit: Slack อนุญาต ~1 request/second สำหรับ search
        time.sleep(1.2)

        # ตรวจสอบว่ายังมีหน้าถัดไปหรือเปล่า
        paging = data.get("messages", {}).get("paging", {})
        if page >= paging.get("pages", 1):
            break

    print(f"  → พบ {len(entries)} messages ที่มี @mention")
    return entries


def entries_to_js(entries: list) -> str:
    """แปลง list of entries → JavaScript const RAW = [...];"""
    # เรียงลำดับจากใหม่ไปเก่า
    entries.sort(key=lambda x: x["_ts"], reverse=True)

    lines = ["const RAW = ["]
    for e in entries:
        mentioned_js   = ", ".join(f"'{m}'" for m in e["mentioned"])
        preview_esc    = e["preview"].replace("\\", "\\\\").replace("'", "\\'")
        channel_esc    = e["channel"].replace("'", "\\'")
        lines.append(
            f"  {{ date:'{e['date']}', sender:'{e['sender']}', "
            f"mentioned:[{mentioned_js}], "
            f"channel:'{channel_esc}', "
            f"topic:'{e['topic']}', "
            f"preview:'{preview_esc}' }},"
        )
    lines.append("];")
    return "\n".join(lines)


def update_html(new_raw_js: str):
    """แทนที่ const RAW = [...]; ใน index.html"""
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"const RAW = \[[\s\S]*?\];"
    if not re.search(pattern, content):
        raise ValueError('ไม่พบ "const RAW = [...];" ใน index.html')

    updated = re.sub(pattern, new_raw_js, content, count=1)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(updated)

    print(f"✅ อัปเดต {HTML_FILE} สำเร็จ")


def main():
    if not SLACK_TOKEN:
        raise EnvironmentError("❌ กรุณาตั้งค่า SLACK_TOKEN environment variable")

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("=" * 50)
    print("  BeNeat Mention Dashboard Updater")
    print(f"  เวลา: {now_str}")
    print("=" * 50)

    all_entries = []

    print("\n[Hood] กำลังดึงข้อมูล...")
    all_entries.extend(fetch_sender_mentions(HOOD_ID, "Hood"))

    print("\n[Pum] กำลังดึงข้อมูล...")
    all_entries.extend(fetch_sender_mentions(PUM_ID, "Pum"))

    print(f"\n📊 รวมทั้งหมด: {len(all_entries)} entries")

    if not all_entries:
        print("⚠️  ไม่พบข้อมูล — คงข้อมูลเดิมไว้")
        return

    raw_js = entries_to_js(all_entries)
    update_html(raw_js)

    print("\n🎉 เสร็จสิ้น! Dashboard พร้อมใช้งาน")


if __name__ == "__main__":
    main()
