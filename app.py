#!/usr/bin/env python3
import os
import threading
import time
import random
import ftplib
import json
import requests
from flask import Flask, jsonify
from datetime import datetime
import pytz

# ---------------- CONFIG ----------------
FTP_HOST = "195.179.226.218"
FTP_PORT = 56421
FTP_USER = "gpftp37275281717442833"
FTP_PASS = "LXNdGShY"
REMOTE_DIR = "/SCUM/Saved/Config/WindowsServer/Loot"

VARIANTS = [f"GeneralZoneModifiers_{i}.json" for i in range(1, 92)]

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1439377206999646208/0WUe3Vl_75zTQtzBCSvC9uDXJdylvEt9VKB0Bes6NviupWMqzcZElGXiMsbg2N6rL5iU"

# Godziny odpaleń: 03:55, 09:55, 15:55, 21:55
RUN_TIMES = [(3, 55), (9, 55), (15, 55), (21, 55)]

TMP_REMOTE_NAME = "._tmp_upload.json"
TARGET_REMOTE_NAME = "GeneralZoneModifiers.json"
# ----------------------------------------

app = Flask(__name__)
_worker_thread = None
_worker_stop = threading.Event()
_last_chosen = None
_last_run_date = None
_lock = threading.Lock()


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
                print(f"[FTP] Uploading temp file {TMP_REMOTE_NAME} ...")
                ftp.storbinary(f"STOR {TMP_REMOTE_NAME}", f)
            try:
                ftp.delete(TARGET_REMOTE_NAME)
            except Exception:
                pass
            ftp.rename(TTMP_REMOTE_NAME, TARGET_REMOTE_NAME)
            print("[FTP] Upload and rename successful.")
        return True
    except Exception as e:
        print("[FTP] Error during FTP upload:", e)
        return False


def send_discord_notification(chosen_file: str):
    print("[Discord] Preparing notification...")
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
            content = f"🎲 **Active Double Loot Zones:** {', '.join(zone_names)}"
        else:
            content = f"🎲 **Wariant loot-u wybrany:** {chosen_file}"
    except Exception as e:
        content = f"🎲 **Wariant loot-u wybrany (błąd odczytu JSON):** {chosen_file} ({e})"

    timestamp = int(time.time())
    content += f"\n⏱ Last draw: <t:{timestamp}:R>"

    try:
        print("[Discord] Sending message:", content)
        r = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=15)
        print(f"[Discord] Response: {r.status_code} {r.text}")
    except Exception as e:
        print("[Discord] Error while sending webhook:", e)


def run_cycle():
    global _last_chosen
    with _lock:
        chosen = choose_variant()
        if _last_chosen is not None and len(VARIANTS) > 1:
            attempts = 0
            while chosen == _last_chosen and attempts < 5:
                chosen = choose_variant()
                attempts += 1
        _last_chosen = chosen

    if not os.path.isfile(chosen):
        print(f"[Cycle] ERROR: local variant file not found: {chosen}")
        return

    print(f"[Cycle] Selected variant: {chosen}")
    ok = upload_to_ftp(chosen)
    if ok:
        send_discord_notification(chosen)
        print(f"[Cycle] Completed successfully for variant: {chosen}")
    else:
        print(f"[Cycle] Upload failed for variant: {chosen}")


# ------------------- NEW SCHEDULING SYSTEM ---------------------

def should_run_now():
    """Sprawdza czy lokalny czas Polski = jeden z harmonogramów."""
    global _last_run_date

    tz = pytz.timezone("Europe/Warsaw")
    now = datetime.now(tz)
    current_hm = (now.hour, now.minute)

    # Jeśli nie jest to żadna wyznaczona godzina → nie uruchamiać
    if current_hm not in RUN_TIMES:
        return False

    # Nie odpalać dwa razy w tej samej minucie
    if _last_run_date == now.date():
        if getattr(should_run_now, "last_minute", None) == now.minute:
            return False

    should_run_now.last_minute = now.minute
    _last_run_date = now.date()
    return True


def background_worker():
    print("[Worker] Scheduler worker started.")
    while not _worker_stop.is_set():
        try:
            if should_run_now():
                print("[Scheduler] Scheduled time hit — running cycle.")
                run_cycle()
        except Exception as e:
            print("[Worker] Exception:", e)

        time.sleep(15)  # sprawdzamy co 15 sekund

    print("[Worker] Scheduler worker stopped.")
# ---------------------------------------------------------------


def start_background_thread():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_stop.clear()
        _worker_thread = threading.Thread(target=background_worker, daemon=True)
        _worker_thread.start()
        print("[Main] Background worker thread started.")


# --- Flask routes ---
@app.route("/", methods=["GET"])
def index():
    return "Loot automation: running", 200


@app.route("/run-now", methods=["POST", "GET"])
def run_now():
    def _runner():
        print("[RunNow] Manual trigger started.")
        run_cycle()
        print("[RunNow] Manual trigger finished.")
    threading.Thread(target=_runner, daemon=True).start()
    return jsonify({"ok": True, "message": "Cycle started in background"}), 202


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "service": "loot-automation",
        "run_times": RUN_TIMES,
        "variants_available": [f for f in VARIANTS if os.path.isfile(f)]
    }), 200


def stop_background_thread():
    _worker_stop.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=5)


# --- Start scheduled worker immediately ---
start_background_thread()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"[Main] Starting Flask on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
