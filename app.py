#!/usr/bin/env python3
import os
import threading
import time
import random
import ftplib
import json
import requests
from flask import Flask, jsonify

# --- Discord ---
import discord
from discord.ext import tasks, commands

# ---------------- CONFIG ----------------
FTP_HOST = "195.179.226.218"
FTP_PORT = 56421
FTP_USER = "gpftp37275281717442833"
FTP_PASS = "LXNdGShY"
REMOTE_DIR = "/SCUM/Saved/Config/WindowsServer/Loot"

VARIANTS = [
    "GeneralZoneModifiers_1.json",
    "GeneralZoneModifiers_2.json",
    "GeneralZoneModifiers_3.json",
    "GeneralZoneModifiers_4.json"
]

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")  # token bota
DISCORD_CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))  # ID kanału do edycji wiadomości

INTERVAL_SECONDS = 4 * 3600
TMP_REMOTE_NAME = "._tmp_upload.json"
TARGET_REMOTE_NAME = "GeneralZoneModifiers.json"
# ----------------------------------------

app = Flask(__name__)
_worker_thread = None
_worker_stop = threading.Event()
_last_chosen = None
_last_run_timestamp = 0
_lock = threading.Lock()

discord_message = None  # obiekt wiadomości bota do aktualizacji

def choose_variant():
    return random.choice(VARIANTS)

def upload_to_ftp(local_file: str) -> bool:
    try:
        print(f"[FTP] Connecting to {FTP_HOST}:{FTP_PORT} ...")
        with ftplib.FTP() as ftp:
            ftp.connect(FTP_HOST, FTP_PORT, timeout=20)
            ftp.login(FTP_USER, FTP_PASS)
            ftp.cwd(REMOTE_DIR)
            with open(local_file, "rb") as f:
                ftp.storbinary(f"STOR {TMP_REMOTE_NAME}", f)
            try:
                ftp.delete(TARGET_REMOTE_NAME)
            except Exception:
                pass
            ftp.rename(TMP_REMOTE_NAME, TARGET_REMOTE_NAME)
        return True
    except Exception as e:
        print("[FTP] Error during FTP upload:", e)
        return False

def send_discord_notification(chosen_file: str):
    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        modifiers = data.get("Modifiers", [])
        zone_names = []
        for mod in modifiers:
            zones = mod.get("Zones", [])
            for z in zones:
                name = z.get("Name")
                if name:
                    zone_names.append(name)
        if zone_names:
            content = f"🎲 **Aktywne strefy loot-u:** {', '.join(zone_names)}"
        else:
            content = f"🎲 **Wariant loot-u wybrany:** {chosen_file}"
    except Exception as e:
        content = f"🎲 **Wariant loot-u wybrany (błąd odczytu JSON):** {chosen_file} ({e})"

    try:
        if DISCORD_CHANNEL_ID != 0:
            bot_channel = discord_client.get_channel(DISCORD_CHANNEL_ID)
            if bot_channel:
                bot_channel.send(content)
        print("[Discord] Notification sent:", content)
    except Exception as e:
        print("[Discord] Error sending Discord notification:", e)

def run_cycle():
    global _last_chosen, _last_run_timestamp
    with _lock:
        chosen = choose_variant()
        if _last_chosen is not None and len(VARIANTS) > 1:
            attempts = 0
            while chosen == _last_chosen and attempts < 5:
                chosen = choose_variant()
                attempts += 1
        _last_chosen = chosen
        _last_run_timestamp = time.time()

    if not os.path.isfile(chosen):
        print(f"[Cycle] ERROR: local variant not found: {chosen}")
        return {"ok": False, "file": chosen}

    print(f"[Cycle] Selected variant: {chosen}")
    ok = upload_to_ftp(chosen)
    if ok:
        send_discord_notification(chosen)
        print(f"[Cycle] Completed successfully")
        return {"ok": True, "file": chosen}
    else:
        print(f"[Cycle] Upload failed")
        return {"ok": False, "file": chosen}

def background_worker():
    print("[Worker] Background worker started. First run executes now.")
    while not _worker_stop.is_set():
        try:
            run_cycle()
        except Exception as e:
            print("[Worker] Exception in run_cycle:", e)

        slept = 0
        while slept < INTERVAL_SECONDS and not _worker_stop.is_set():
            time.sleep(1)
            slept += 1
    print("[Worker] Background worker stopped.")

# ---------------- Discord bot ----------------
intents = discord.Intents.default()
intents.messages = True
discord_client = commands.Bot(command_prefix="!", intents=intents)

@discord_client.event
async def on_ready():
    print(f"[Discord] Bot connected as {discord_client.user}")
    if DISCORD_CHANNEL_ID != 0:
        channel = discord_client.get_channel(DISCORD_CHANNEL_ID)
        global discord_message
        if channel:
            # utwórz wiadomość jeśli nie istnieje
            discord_message = await channel.send("⏱ Czekam na pierwsze losowanie...")
            update_clock.start()  # uruchom task aktualizacji zegara

@tasks.loop(seconds=1)
async def update_clock():
    global discord_message
    if discord_message is None:
        return
    if _last_run_timestamp == 0:
        text = "⏱ Czekam na pierwsze losowanie..."
    else:
        elapsed = int(time.time() - _last_run_timestamp)
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        text = f"⏱ Czas od ostatniego losowania: {h:02d}:{m:02d}:{s:02d}"
    try:
        await discord_message.edit(content=text)
    except Exception as e:
        print("[Discord] Error updating clock:", e)

# --- Flask routes ---
@app.route("/", methods=["GET"])
def index():
    return "Loot automation: running", 200

@app.route("/run-now", methods=["POST", "GET"])
def run_now():
    threading.Thread(target=run_cycle, daemon=True).start()
    return jsonify({"ok": True}), 202

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "service": "loot-automation",
        "interval_hours": INTERVAL_SECONDS // 3600,
        "variants_available": [f for f in VARIANTS if os.path.isfile(f)]
    }), 200

def start_background_thread():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_stop.clear()
        _worker_thread = threading.Thread(target=background_worker, daemon=True)
        _worker_thread.start()
        print("[Main] Background worker thread started.")

if __name__ == "__main__":
    start_background_thread()
    port = int(os.environ.get("PORT", 10000))
    print(f"[Main] Starting Flask on 0.0.0.0:{port}")
    
    # uruchom Flask i bota w tle
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port), daemon=True).start()
    discord_client.run(DISCORD_TOKEN)
