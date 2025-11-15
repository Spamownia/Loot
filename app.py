#!/usr/bin/env python3
import os
import threading
import time
import random
import ftplib
import json
import requests
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

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1438609916238762054/FYjetBfGOUQgK4i9VIGhXVUjTbO_KxY1NYHcUsHv6Cpqcrj0hEaQllaqysQYVlydGDjl"

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

# tekst zegara
_clock_text = "Clock not started yet"


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
            ftp.rename(TMP_REMOTE_NAME, TARGET_REMOTE_NAME)
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
            content = f"🎲 **Aktywne strefy loot-u:** {', '.join(zone_names)}"
        else:
            content = f"🎲 **Wariant loot-u wybrany:** {chosen_file}"
    except Exception as e:
        content = f"🎲 **Wariant loot-u wybrany (błąd odczytu JSON):** {chosen_file} ({e})"

    try:
        print("[Discord] Sending message:", content)
        r = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=15)
        print(f"[Discord] Response: {r.status_code} {r.text}")
    except Exception as e:
        print("[Discord] Error while sending webhook:", e)


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


def clock_worker():
    """Aktualizuje _clock_text co sekundę BEZ generowania logów."""
    global _clock_text

    while not _worker_stop.is_set():
        if _last_run_timestamp == 0:
            _clock_text = "Czekam na pierwsze losowanie..."
        else:
            elapsed = int(time.time() - _last_run_timestamp)
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            _clock_text = f"Czas od ostatniego losowania: {h:02d}:{m:02d}:{s:02d}"
        time.sleep(1)


def start_background_thread():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_stop.clear()
        _worker_thread = threading.Thread(target=background_worker, daemon=True)
        _worker_thread.start()
        print("[Main] Background worker thread started.")


def start_clock_thread():
    t = threading.Thread(target=clock_worker, daemon=True)
    t.start()
    print("[Main] Clock thread started.")


# --- Flask routes ---
@app.route("/", methods=["GET"])
def index():
    return "Loot automation: running", 200


@app.route("/run-now", methods=["POST", "GET"])
def run_now():
    def _runner():
        try:
            print("[RunNow] Manual trigger started.")
            run_cycle()
            print("[RunNow] Manual trigger finished.")
        except Exception as e:
            print("[RunNow] Exception:", e)
    threading.Thread(target=_runner, daemon=True).start()
    return jsonify({"ok": True}), 202


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "service": "loot-automation",
        "interval_hours": INTERVAL_SECONDS // 3600,
        "variants_available": [f for f in VARIANTS if os.path.isfile(f)]
    }), 200


@app.route("/clock", methods=["GET"])
def clock_status():
    return _clock_text, 200


def stop_background_thread():
    _worker_stop.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=5)


# --- Start threads ---
start_background_thread()
start_clock_thread()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"[Main] Starting Flask on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
