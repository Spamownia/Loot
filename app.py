#!/usr/bin/env python3
# app.py -- single-file web service + background loop (4h) for uploading loot variants to FTP and notifying Discord

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

INTERVAL_SECONDS = 4 * 3600  # 4 godziny
TMP_REMOTE_NAME = "._tmp_upload.json"
TARGET_REMOTE_NAME = "GeneralZoneModifiers.json"
LOG_FILE = "loot_log.txt"
# ----------------------------------------

app = Flask(__name__)
_worker_thread = None
_worker_stop = threading.Event()
_last_chosen = None
_lock = threading.Lock()


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def choose_variant():
    return random.choice(VARIANTS)


def upload_to_ftp(local_file: str) -> bool:
    try:
        log(f"[FTP] Connecting to {FTP_HOST}:{FTP_PORT} ...")
        with ftplib.FTP() as ftp:
            ftp.connect(FTP_HOST, FTP_PORT, timeout=20)
            ftp.login(FTP_USER, FTP_PASS)
            ftp.cwd(REMOTE_DIR)
            with open(local_file, "rb") as f:
                log(f"[FTP] Uploading temp file {TMP_REMOTE_NAME} ...")
                ftp.storbinary(f"STOR {TMP_REMOTE_NAME}", f)
            try:
                ftp.delete(TARGET_REMOTE_NAME)
            except Exception:
                pass
            ftp.rename(TMP_REMOTE_NAME, TARGET_REMOTE_NAME)
            log("[FTP] Upload and rename successful.")
        return True
    except Exception as e:
        log(f"[FTP] Error during upload: {e}")
        return False


def send_discord_notification(chosen_file: str):
    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        zones = data.get("Zones", [])
        zone_names = [z.get("Name", "Unknown") for z in zones]
        content = f"🎲 **Aktywna strefa loot-u:** {', '.join(zone_names)}"
    except Exception as e:
        content = f"❌ Nie udało się odczytać nazwy strefy z {chosen_file}: {e}"

    try:
        r = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=15)
        if r.status_code in (200, 204):
            log(f"[Discord] Notification sent: {content}")
        else:
            log(f"[Discord] Unexpected status {r.status_code}: {r.text}")
    except Exception as e:
        log(f"[Discord] Error while sending webhook: {e}")


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
        log(f"[Cycle] ERROR: local variant file not found: {chosen}")
        return {"ok": False, "reason": "missing_variant", "file": chosen}

    log(f"[Cycle] Selected variant: {chosen}")
    ok = upload_to_ftp(chosen)
    if ok:
        send_discord_notification(chosen)
        log(f"[Cycle] Completed successfully for variant: {chosen}")
        return {"ok": True, "file": chosen}
    else:
        log(f"[Cycle] Upload failed for variant: {chosen}")
        return {"ok": False, "file": chosen}


def background_worker():
    log("[Worker] Background worker started. First run will execute immediately.")
    while not _worker_stop.is_set():
        try:
            run_cycle()
        except Exception as e:
            log(f"[Worker] Exception in run_cycle: {e}")
        slept = 0
        while slept < INTERVAL_SECONDS and not _worker_stop.is_set():
            time.sleep(1)
            slept += 1
    log("[Worker] Background worker stopped.")


@app.route("/", methods=["GET"])
def index():
    return "Loot automation: running", 200


@app.route("/run-now", methods=["POST", "GET"])
def run_now():
    def _runner():
        try:
            log("[RunNow] Manual trigger started.")
            run_cycle()
            log("[RunNow] Manual trigger finished.")
        except Exception as e:
            log(f"[RunNow] Exception: {e}")

    threading.Thread(target=_runner, daemon=True).start()
    return jsonify({"ok": True, "message": "Cycle started in background"}), 202


@app.route("/status", methods=["GET"])
def status():
    available = [f for f in VARIANTS if os.path.isfile(f)]
    return jsonify({
        "service": "loot-automation",
        "interval_hours": INTERVAL_SECONDS // 3600,
        "variants_available": available
    }), 200


def start_background_thread():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_stop.clear()
        _worker_thread = threading.Thread(target=background_worker, daemon=True)
        _worker_thread.start()
        log("[Main] Background worker thread started.")


def stop_background_thread():
    _worker_stop.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=5)


if __name__ == "__main__":
    start_background_thread()
    run_cycle()  # first immediate cycle
    port = int(os.environ.get("PORT", 10000))
    log(f"[Main] Starting Flask on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
