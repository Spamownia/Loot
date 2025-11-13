import ftplib
import random
import os
import sys
import requests
import json
import time

# ---------- USTAWIENIA ----------
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

# Token G-Portal i ID serwera
GP_TOKEN = "<TWOJ_TOKEN_GPORTAL>"
GP_SERVER_ID = "<TWOJE_ID_SERWERA>"

# Interwał automatycznego uploadu (sekundy)
INTERVAL_SECONDS = 4 * 3600  # 4h
# ---------------------------------

def choose_variant():
    return random.choice(VARIANTS)

def upload(local_file, remote_path):
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(FTP_HOST, FTP_PORT, timeout=15)
            ftp.login(FTP_USER, FTP_PASS)
            ftp.cwd(remote_path)
            tmp_name = "._tmp_upload.json"
            print(f"⏫ Wysyłanie pliku {local_file}...")
            with open(local_file, "rb") as f:
                ftp.storbinary(f"STOR {tmp_name}", f)
            try:
                ftp.delete("GeneralZoneModifiers.json")
            except Exception:
                pass
            ftp.rename(tmp_name, "GeneralZoneModifiers.json")
            print("✅ Wgrano i podmieniono GeneralZoneModifiers.json na serwerze.")
    except Exception as e:
        print("❌ Błąd FTP:", e)

def send_discord_notification(chosen_file):
    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        zones = data.get("Zones", [])
        zone_names = [z.get("Name", "Unknown") for z in zones]
        content = f"🎲 **Aktywna strefa loot-u:** {', '.join(zone_names)}"
    except Exception as e:
        content = f"❌ Nie udało się odczytać nazwy strefy: {e}"

    try:
        r = requests.post(DISCORD_WEBHOOK, json={"content": content})
        if r.status_code in (200, 204):
            print(f"✅ Wysłano powiadomienie Discord: {content}")
        else:
            print(f"❌ Błąd wysyłki Discord: {r.status_code} {r.text}")
    except Exception as e:
        print(f"❌ Błąd połączenia z Discord: {e}")

def restart_gportal():
    """Restart serwera SCUM przez API G-Portal"""
    url = f"https://api.g-portal.com/server/{GP_SERVER_ID}/restart"
    headers = {
        "Authorization": f"Bearer {GP_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        r = requests.post(url, headers=headers)
        if r.status_code == 200:
            print("🔄 Serwer został zrestartowany pomyślnie.")
        else:
            print(f"❌ Błąd restartu serwera: {r.status_code} {r.text}")
    except Exception as e:
        print(f"❌ Wyjątek przy próbie restartu: {e}")

def run_cycle():
    chosen = choose_variant()
    if not os.path.isfile(chosen):
        print(f"❌ Brak pliku lokalnego: {chosen}")
        return
    print("🎲 Wybrano wariant:", chosen)
    upload(chosen, REMOTE_DIR)
    send_discord_notification(chosen)
    restart_gportal()
    print("ℹ️ Cykl zakończony.")

if __name__ == "__main__":
    print("🟢 Skrypt uruchomiony w trybie 4h loop z pełną automatyzacją.")
    while True:
        run_cycle()
        print(f"⏱ Oczekiwanie {INTERVAL_SECONDS // 3600}h do kolejnego losowania...")
        time.sleep(INTERVAL_SECONDS)
