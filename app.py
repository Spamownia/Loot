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
# FTP
FTP_HOST = "195.179.226.218"
FTP_PORT = 56421
FTP_USER = "gpftp37275281717442833"
FTP_PASS = "LXNdGShY"
REMOTE_DIR = "/SCUM/Saved/Config/WindowsServer/Loot"

# Local variant files (must be present in the same directory)
VARIANTS = [
    "GeneralZoneModifiers_1.json",
    "GeneralZoneModifiers_2.json",
    "GeneralZoneModifiers_3.json",
    "GeneralZoneModifiers_4.json"
]

# Discord webhook
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1438609916238762054/FYjetBfGOUQgK4i9VIGhXVUjTbO_KxY1NYHcUsHv6Cpqcrj0hEaQllaqysQYVlydGDjl"

# Interval (seconds)
INTERVAL_SECONDS = 4 * 3600  # 4 hours

# Safe temporary upload filename on FTP
TMP_REMOTE_NAME = "._tmp_upload.json"
TARGET_REMOTE_NAME = "GeneralZoneModifiers.json"
# ----------------------------------------

app = Flask(__name__)

# Thread control
_worker_thread = None
_worker_stop = threading.Event()
_last_chosen = None
_lock = threading.Lock()


def choose_variant():
    """Randomly choose a variant file from VARIANTS."""
    return random.choice(VARIANTS)


def upload_to_ftp(local_file: str) -> bool:
    """Upload a local file to the FTP remote path, atomically (upload -> rename)."""
    try:
        print(f"[FTP] Connecting to {FTP_HOST}:{FTP_PORT} ...")
        with ftplib.FTP() as ftp:
            ftp.connect(FTP_HOST, FTP_PORT, timeout=20)
            ftp.login(FTP_USER, FTP_PASS)
            # navigate to remote dir (create? assume exists)
            try:
                ftp.cwd(REMOTE_DIR)
            except Exception as e:
                print(f"[FTP] Could not cwd to {REMOTE_DIR}: {e}")
                # try to create path? For safety, fail
                return False

            # upload as tmp file first
            with open(local_file, "rb") as f:
                print(f"[FTP] Uploading temp file {TMP_REMOTE_NAME} ...")
                ftp.storbinary(f"STOR {TMP_REMOTE_NAME}", f)

            # remove existing and rename
            try:
                ftp.delete(TARGET_REMOTE_NAME)
            except Exception:
                # ignore if doesn't exist
                pass

            ftp.rename(TMP_REMOTE_NAME, TARGET_REMOTE_NAME)
            print("[FTP] Upload and rename successful.")
        return True
    except Exception as e:
        print("[FTP] Error during FTP upload:", e)
        return False


def send_discord_notification(chosen_file: str):
    """Read Zones from chosen file and post a message to Discord webhook."""
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
            print("[Discord] Notification sent:", content)
        else:
            print(f"[Discord] Unexpected status {r.status_code}: {r.text}")
    except Exception as e:
        print("[Discord] Error while sending webhook:", e)


def run_cycle():
    """Run a single cycle: choose variant, upload, notify. Safe to call repeatedly."""
    global _last_chosen
    with _lock:
        chosen = choose_variant()
        # prevent immediate same-file twice in a row (small improvement)
        if _last_chosen is not None and len(VARIANTS) > 1:
            attempts = 0
            while chosen == _last_chosen and attempts < 5:
                chosen = choose_variant()
                attempts += 1

        _last_chosen = chosen

    if not os.path.isfile(chosen):
        print(f"[Cycle] ERROR: local variant file not found: {chosen}")
        return {"ok": False, "reason": "missing_variant", "file": chosen}

    print(f"[Cycle] Selected variant: {chosen}")
    ok = upload_to_ftp(chosen)
    if ok:
        send_discord_notification(chosen)
        print(f"[Cycle] Completed successfully for variant: {chosen}")
        return {"ok": True, "file": chosen}
    else:
        print(f"[Cycle] Upload failed for variant: {chosen}")
        return {"ok": False, "file": chosen}


def background_worker():
    """Background loop executed in a dedicated thread. Runs until _worker_stop is set."""
    print("[Worker] Background worker started. First run will execute immediately.")
    while not _worker_stop.is_set():
        try:
            result = run_cycle()
            # result logged already; you can extend to write to file
        except Exception as e:
            print("[Worker] Exception in run_cycle:", e)

        # wait INTERVAL_SECONDS but wake early if stop requested
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
    """Trigger immediate run_cycle in background and return immediately."""
    def _runner():
        try:
            print("[RunNow] Manual trigger started.")
            run_cycle()
            print("[RunNow] Manual trigger finished.")
        except Exception as e:
            print("[RunNow] Exception:", e)

    threading.Thread(target=_runner, daemon=True).start()
    return jsonify({"ok": True, "message": "Cycle started in background"}), 202


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


def stop_background_thread():
    _worker_stop.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=5)


if __name__ == "__main__":
    # Start background worker and Flask (port from env or 10000)
    start_background_thread()
    port = int(os.environ.get("PORT", 10000))
    print(f"[Main] Starting Flask on 0.0.0.0:{port}")
    # Flask will serve and keep process alive so Render sees a bound port
    app.run(host="0.0.0.0", port=port)
