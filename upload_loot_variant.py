# upload_loot_variant.py
# Wersja: z powiadomieniem na Discord
import ftplib
import random
import os
import sys
import requests

# ------- USTAWIENIA -------
FTP_HOST = "195.179.226.218"
FTP_PORT = 56421
FTP_USER = "gpftp37275281717442833"
FTP_PASS = "LXNdGShY"
REMOTE_DIR = "/SCUM/Saved/Config/WindowsServer/Loot"

# Lista dostępnych wariantów pliku (muszą znajdować się lokalnie)
VARIANTS = [
    "GeneralZoneModifiers_1.json",
    "GeneralZoneModifiers_2.json",
    "GeneralZoneModifiers_3.json"
]

# Webhook Discord
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1438609916238762054/FYjetBfGOUQgK4i9VIGhXVUjTbO_KxY1NYHcUsHv6Cpqcrj0hEaQllaqysQYVlydGDjl"
# ---------------------------

def choose_variant():
    """Losowo wybiera plik wariantu."""
    return random.choice(VARIANTS)

def upload(local_file, remote_path):
    """Łączy się przez FTP, wysyła plik i podmienia GeneralZoneModifiers.json."""
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
        sys.exit(1)

def send_discord_notification(chosen_file):
    """Wysyła informację o aktywnej strefie na Discorda."""
    # Wyciągamy nazwę strefy z pliku JSON
    import json
    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        zones = data.get("Zones", [])
        zone_names = [z.get("Name", "Unknown") for z in zones]
        content = f"🎲 **Aktywna strefa loot-u:** {', '.join(zone_names)}"
    except Exception as e:
        content = f"❌ Nie udało się odczytać nazwy strefy: {e}"

    # Wyślij na Discord
    try:
        r = requests.post(DISCORD_WEBHOOK, json={"content": content})
        if r.status_code == 204 or r.status_code == 200:
            print(f"✅ Wysłano powiadomienie Discord: {content}")
        else:
            print(f"❌ Błąd wysyłki Discord: {r.status_code} {r.text}")
    except Exception as e:
        print(f"❌ Błąd połączenia z Discord: {e}")

if __name__ == "__main__":
    chosen = choose_variant()
    if not os.path.isfile(chosen):
        print(f"❌ Brak pliku lokalnego: {chosen}")
        sys.exit(1)

    print("🎲 Wybrano wariant:", chosen)
    upload(chosen, REMOTE_DIR)
    send_discord_notification(chosen)
    print("ℹ️ Upload zakończony. Teraz wykonaj restart serwera z panelu G-Portal.")
