#!/usr/bin/env python3
import os
import threading
import time
import random
import ftplib
import json
import asyncio
import discord
from discord.ext import tasks, commands
from flask import Flask, jsonify

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
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL", 0))  # kanał do wysyłki

INTERVAL_SECONDS = 4 * 3600
TMP_REMOTE_NAME = "._tmp_upload.json"
TARGET_REMOTE_NAME = "GeneralZoneModifiers.json"
# ----------------------------------------

app = Flask(__name__)
_last_chosen = None
_last_run_timestamp = 0
_lock = threading.Lock()
bot_message = None  # referencja do wiadomości na Discordzie

# --- FTP i losowanie ---
def choose_variant():
    return random.choice(VARIANTS)

def upload_to_ftp(local_file: str) -> bool:
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(FTP_HOST, FTP_PORT, timeout=20)
            ftp.login(FTP_USER, FTP_PASS)
            ftp.cwd(REMOTE_DIR)
            with open(local_file, "rb") as f:
                ftp.storbinary(f"STOR {TMP_REMOTE_NAME}", f)
            try: ftp.delete(TARGET_REMOTE_NAME)
            except: pass
            ftp.rename(TMP_REMOTE_NAME, TARGET_REMOTE_NAME)
        return True
    except Exception as e:
        print("[FTP] Error:", e)
        return False

def get_active_zones(chosen_file):
    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        modifiers = data.get("Modifiers", [])
        zones = []
        for mod in modifiers:
            for z in mod.get("Zones", []):
                name = z.get("Name")
                if name:
                    zones.append(name)
        return zones
    except:
        return []

async def run_cycle(bot=None):
    global _last_chosen, _last_run_timestamp, bot_message
    with _lock:
        chosen = choose_variant()
        if _last_chosen is not None and len(VARIANTS) > 1:
            attempts = 0
            while chosen == _last_chosen and attempts < 5:
                chosen = choose_variant()
                attempts += 1
        _last_chosen = chosen
        _last_run_timestamp = time.time()

    print(f"[Cycle] Selected variant: {chosen}")
    ok = upload_to_ftp(chosen)
    if ok:
        zones = get_active_zones(chosen)
        content = f"🎲 **Aktywne strefy loot-u:** {', '.join(zones) if zones else chosen}\n⏱ Czas od ostatniego losowania: 00:00:00"
        if bot and CHANNEL_ID:
            channel = bot.get_channel(CHANNEL_ID)
            if channel:
                if bot_message is None:
                    bot_message = await channel.send(content)
                else:
                    await bot_message.edit(content=content)
        print("[Cycle] Completed successfully")
        return True
    else:
        print("[Cycle] Upload failed")
        return False

# --- Discord bot ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print(f"[Discord] Logged in as {bot.user}")
    clock_loop.start()
    await run_cycle(bot)

@bot.command()
async def run_now(ctx):
    """Ręczne wywołanie losowania."""
    await run_cycle(bot)
    await ctx.send("🔄 Losowanie stref zostało wykonane.")

# --- zegar ---
@tasks.loop(seconds=1.0)
async def clock_loop():
    global bot_message
    if bot_message is None or _last_run_timestamp == 0:
        return
    elapsed = int(time.time() - _last_run_timestamp)
    h = elapsed // 3600
    m = (elapsed % 3600) // 60
    s = elapsed % 60
    # aktualizujemy tylko treść zegara w istniejącej wiadomości
    content = bot_message.content.split("\n")[0] + f"\n⏱ Czas od ostatniego losowania: {h:02d}:{m:02d}:{s:02d}"
    await bot_message.edit(content=content)

# --- Flask ---
@app.route("/", methods=["GET"])
def index():
    return "Loot automation: running", 200

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "service": "loot-automation",
        "interval_hours": INTERVAL_SECONDS // 3600,
        "variants_available": [f for f in VARIANTS if os.path.isfile(f)]
    }), 200

def start_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- uruchomienie ---
if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    bot.run(DISCORD_TOKEN)
