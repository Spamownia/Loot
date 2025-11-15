#!/usr/bin/env python3
# app.py -- single-file web service + background loop (4h) for uploading loot variants to FTP and notifying Discord
# with enhanced error handling

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

INTERVAL_SECONDS = 4 * 3600  # 4h
TMP_REMOTE_NAME = "._tmp_upload.json"
TARGET_REMOTE_NAME = "GeneralZoneModifiers.json"
# ----------------------------------------

app = Flask(__name__)

_worker_thread = None
_worker_stop = threading.Event()
_last_chosen = None
_lock = threading.Lock()


def choose_variant():
    return random.choice(VARIANTS)


def upload_to_ftp(local_file: str) -> bool:
    try:
        print(f"[FTP] Connecting to {FTP_HOST}:{FTP_PORT} ...")
        with ftplib.FTP() as ftp:
            ftp.connect(FTP_HOST, FTP_PORT, timeout=20)
            ftp.login(FTP_USER, FTP_PASS)
            try:
                ftp.cwd(REMOTE_DIR)
            except Exception as e:
                print(f"[FTP] ERROR: cannot cwd to {REMOTE_DIR}: {e}")
                return False
            try:
                with open(local_file, "rb") as f:
                    ftp.storbinary(f"STOR {TMP_REMOTE_NAME}", f)
                try:
                    ftp.delete(TARGET_REMOTE_NAME)
                except Exception:
                    pass
                ftp.rename(TMP_REMOTE_NAME, TARGET_REMOTE_NAME)
                print(f"[FTP] Upload successful: {local_file} -> {TARGET_REMOTE_NAME}")
                return True
            except Exception as e:
                print(f"[FTP] ERROR uploading file {local_file}: {e}")
                return False
    except Exception as e:
        print(f"[FTP] Connection/login failed: {e}")
        return False


def send_discord_notification(chosen_file: str):
    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        zones = data.get("Zones", [])
        zone_names = [z.get("Name", "Unknown") for z in zones]
        content = f"🎲 **Active loot zones:** {', '.join(zone_names)}"
    except Exception as e:
        content = f"❌ Failed to read zones from {chosen_file}: {e}"

    try:
        r = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=15)
        if r.status_code in (200, 204):
            print(f"[Discord] Notification sent: {content}")
        else:
            print(f"[Discord] ERROR {r.status_code}: {r.text}")
    except requests.exceptions.RequestException as e:
        print(f"[Discord] Connection error: {e}")


def run_cycle():
    global _last_chosen
    with _lock:
        chosen = choose_variant()
        if _last_chosen and len(VARIANTS) > 1:
            attempts = 0
            while chosen == _last_chosen and attempts < 5:
                chosen = choose_variant()
                attempts += 1
        _last_chosen = chosen

    chosen_path = os.path.join(os.getcwd(), chosen)
    if not os.path.isfile(chosen_path):
        print(f"[Cycle] ERROR: local variant file missing: {chosen_path}")
        return {"ok": False, "file": chosen}

    print(f"[Cycle] Selected variant: {chosen_path}")
    if upload_to_ftp(chosen_path):
        send_discord_notification(chosen_path)
        print(f"[Cycle] Completed successfully for: {chosen_path}")
        return {"ok": True, "file": chosen}
    else:
        print(f"[Cycle] Upload failed for: {chosen_path}")
        return {"ok": False, "file": chosen}


def background_worker():
    print("[Worker] Background worker started.")
    while not _worker_stop.is_set():
        try:
            run_cycle()
        except Exception as e:
            print(f"[Worker] Exception in run_cycle: {e}")

        slept = 0
        while slept < INTERVAL_SECONDS and not _worker_stop.is_set():
            time.sleep(1)
            slept += 1
    print("[Worker] Background worker stopped.")


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
            print(f"[RunNow] Exception: {e}")

    threading.Thread(target=_runner, daemon=True).start()
    return jsonify({"ok": True, "message": "Cycle started in background"}), 202


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "service": "loot-automation",
        "interval_hours": INTERVAL_SECONDS // 3600,
        "variants_available": [f for f in VARIANTS if os.path.isfile(os.path.join(os.getcwd(), f))]
    }), 200


def start_background_thread():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_stop.clear()
        _worker_thread = threading.Thread(target=background_worker, daemon=True)
        _worker_thread.start()
        print("[Main] Background worker thread started.")


if __name__ == "__main__":
    print("[Main] Running initial cycle before Flask + background threads")
    run_cycle()  # immediate first run
    start_background_thread()
    port = int(os.environ.get("PORT", 10000))
    print(f"[Main] Starting Flask on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
