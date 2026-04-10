"""
DentVantage SA Agent — User Management
Role: owner (plný přístup) / assistant (pouze SA inventura)
Schválení nového uživatele přes Telegram od ownera.
Škálovatelné: config.json per ordinace, žádné env vars pro uživatele.
"""

import json
import os
from datetime import datetime
from typing import Optional

CONFIG_PATH = os.environ.get("SA_CONFIG_PATH", "sa_config.json")

# ── Role a jejich oprávnění ─────────────────────────────────
ROLE_PRAVA = {
    "owner": [
        "sklad_read", "sklad_write",
        "objednavky_schvalovat", "objednavky_read",
        "users_manage",
        "check_spustit",
        "all_prikazy",
    ],
    "assistant": [
        "sklad_read", "sklad_write",
        "inventura",
    ],
    "pending": [],  # čeká na schválení ownera
}

# ── Příkazy povolené per role ───────────────────────────────
PRIKAZY_ROLE = {
    "owner":     ["/sklad", "/pridat", "/spotreba", "/check", "/inventura",
                  "/uzivatele", "/pridat_uzivatele", "/odebrat_uzivatele"],
    "assistant": ["/inventura", "/sklad"],
    "pending":   [],
}


def nacti_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def uloz_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_user(chat_id: str) -> Optional[dict]:
    """Vrátí uživatele podle chat_id nebo None."""
    cfg = nacti_config()
    for u in cfg["sa"].get("users", []):
        if str(u["chat_id"]) == str(chat_id):
            return u
    return None


def get_owner(cfg: dict = None) -> Optional[dict]:
    """Vrátí prvního ownera ordinace."""
    if cfg is None:
        cfg = nacti_config()
    for u in cfg["sa"].get("users", []):
        if u["role"] == "owner" and u.get("aktivni", True):
            return u
    return None


def ma_pravo(chat_id: str, pravo: str) -> bool:
    """Zkontroluje jestli má uživatel dané oprávnění."""
    user = get_user(chat_id)
    if not user or not user.get("aktivni", True):
        return False
    role = user.get("role", "pending")
    return pravo in ROLE_PRAVA.get(role, [])


def prikaz_povolen(chat_id: str, prikaz: str) -> bool:
    """Zkontroluje jestli smí uživatel použít příkaz."""
    user = get_user(chat_id)
    if not user or not user.get("aktivni", True):
        return False
    role = user.get("role", "pending")
    povolene = PRIKAZY_ROLE.get(role, [])
    # owner má všechno
    if role == "owner":
        return True
    return prikaz in povolene


def registruj_pending(chat_id: str, jmeno: str) -> bool:
    """
    Přidá nového uživatele jako 'pending'.
    Vrátí True pokud byl přidán, False pokud už existuje.
    """
    cfg = nacti_config()
    users = cfg["sa"].setdefault("users", [])

    # Zkontroluj jestli už existuje
    for u in users:
        if str(u["chat_id"]) == str(chat_id):
            return False

    users.append({
        "chat_id": str(chat_id),
        "jmeno": jmeno,
        "role": "pending",
        "aktivni": False,
        "registrovan": datetime.utcnow().isoformat()
    })
    uloz_config(cfg)
    return True


def schval_uzivatele(chat_id: str, role: str = "assistant") -> bool:
    """Owner schválí pending uživatele a přiřadí mu roli."""
    cfg = nacti_config()
    for u in cfg["sa"].get("users", []):
        if str(u["chat_id"]) == str(chat_id):
            u["role"] = role
            u["aktivni"] = True
            u["schvalen"] = datetime.utcnow().isoformat()
            uloz_config(cfg)
            return True
    return False


def zamitni_uzivatele(chat_id: str) -> bool:
    """Owner zamítne nebo odebere uživatele."""
    cfg = nacti_config()
    users = cfg["sa"].get("users", [])
    puvodni = len(users)
    cfg["sa"]["users"] = [u for u in users if str(u["chat_id"]) != str(chat_id)]
    if len(cfg["sa"]["users"]) < puvodni:
        uloz_config(cfg)
        return True
    return False


def seznam_uzivatelu() -> list:
    """Vrátí seznam všech uživatelů ordinace."""
    cfg = nacti_config()
    return cfg["sa"].get("users", [])


# ── Telegram texty ──────────────────────────────────────────

def text_zadost_o_pristup(chat_id: str, jmeno: str, ordinace: str) -> tuple[str, dict]:
    """
    Zpráva pro ownera — nový uživatel žádá o přístup.
    Vrátí (text, inline_keyboard).
    """
    text = (
        f"👤 <b>Nový uživatel žádá o přístup</b>\n\n"
        f"Jméno: <b>{jmeno}</b>\n"
        f"Telegram ID: <code>{chat_id}</code>\n"
        f"Ordinace: {ordinace}\n\n"
        f"Jakou roli mu přiřadit?"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Asistentka (sklad)", "callback_data": f"user_schval_{chat_id}_assistant"},
            {"text": "❌ Zamítnout",          "callback_data": f"user_zamit_{chat_id}"},
        ]]
    }
    return text, keyboard


def text_vitejte(jmeno: str, role: str) -> str:
    """Uvítací zpráva pro nově schváleného uživatele."""
    if role == "assistant":
        return (
            f"👋 Vítej, <b>{jmeno}</b>!\n\n"
            f"Máš přístup do SA Agenta — skladového asistenta ordinace.\n\n"
            f"Co můžeš dělat:\n"
            f"• /inventura — vyfotit zásoby a zapsat do skladu\n"
            f"• /sklad — zobrazit aktuální stav zásob\n\n"
            f"Stačí poslat fotku zboží a napsat počet kusů. 📦"
        )
    return f"👋 Vítej, <b>{jmeno}</b>! Přístup byl aktivován."


def text_pristup_odmitnuto() -> str:
    return (
        "⛔ Přístup nebyl povolen.\n"
        "Pokud si myslíš, že jde o chybu, kontaktuj doktora."
    )


def text_neznam_uzivatele() -> str:
    return (
        "👋 Ahoj! Ještě tě neznám.\n\n"
        "Pro přístup do SA Agenta potřebuješ schválení doktora.\n"
        "Pošli zprávu /start a doktor dostane žádost o přístup."
    )
