"""
DentVantage SA Agent — hlavní server
FastAPI na portu 8002 + Telegram approval flow + scheduler
"""

import os
import json
import threading
import time
import requests
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from sklad import (
    init_db, get_vsechny_zasob, get_material, get_config,
    update_zasoba, pridat_spotreba, pridat_dodavku,
    check_nizke_zasoby, uloz_objednavku, schval_objednavku,
    zamitni_objednavku, zkontroluj_zdrazeni, uloz_cenu,
    predikuj_dny_do_dochazeni
)
from sa_agent import navrhni_objednavky, zpracuj_telegram_prikaz, fa_signal_text
from users import (
    get_user, get_owner, prikaz_povolen, ma_pravo,
    registruj_pending, schval_uzivatele, zamitni_uzivatele,
    seznam_uzivatelu, text_zadost_o_pristup, text_vitejte,
    text_pristup_odmitnuto, text_neznam_uzivatele
)

# ─────────────────────────────────────────────
# KONFIGURACE
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("SA_TELEGRAM_CHAT_ID", "5858139701")
PORT = int(os.environ.get("SA_PORT", 8002))

app = FastAPI(title="DentVantage SA Agent", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ─────────────────────────────────────────────
# TELEGRAM HELPERS
# ─────────────────────────────────────────────
def tg_send(text: str, reply_markup: dict = None, chat_id: str = TELEGRAM_CHAT_ID):
    if not TELEGRAM_BOT_TOKEN:
        print(f"[SA TG] {text}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[SA TG ERROR] {e}")


def tg_answer_callback(callback_query_id: str, text: str = ""):
    if not TELEGRAM_BOT_TOKEN:
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id, "text": text},
        timeout=5
    )


def tg_edit_message(chat_id: str, message_id: int, text: str):
    if not TELEGRAM_BOT_TOKEN:
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText",
        json={"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"},
        timeout=5
    )


def posli_upozorneni_material(material: dict, obj_id: int):
    """Pošle Telegram zprávu s approval tlačítky pro jeden materiál."""
    dny = predikuj_dny_do_dochazeni(material)
    dny_str = f"~{dny} dní" if dny else "brzy"
    cena_celkem = material["objednat_ks"] * material["cena_kc"]

    text = (
        f"⚠️ <b>SKLAD: {material['nazev']}</b>\n\n"
        f"📦 Zbývá: <b>{material['zasoba']} {material['jednotka']}</b> "
        f"(min. {material['minimum']})\n"
        f"⏱ Dojde za: <b>{dny_str}</b>\n\n"
        f"🛒 Navrhuji objednat: <b>{material['objednat_ks']} ks</b>\n"
        f"💰 Cena: <b>{cena_celkem:.0f} Kč</b> "
        f"({material['cena_kc']} Kč/ks)\n"
        f"🏢 Dodavatel: {material.get('dodavatel_id', '?')}"
    )

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Schválit", "callback_data": f"sa_schvalit_{obj_id}"},
            {"text": "⏰ Odložit 3 dny", "callback_data": f"sa_odlozit_{obj_id}_3"},
            {"text": "❌ Zamítnout", "callback_data": f"sa_zamitit_{obj_id}"}
        ]]
    }
    tg_send(text, reply_markup=keyboard)


# ─────────────────────────────────────────────
# TÝDENNÍ CHECK
# ─────────────────────────────────────────────
def tydenni_check():
    """Zkontroluje zásoby a pošle notifikace pro materiály pod minimem."""
    print(f"[SA] Týdenní check zásoby — {datetime.now().isoformat()}")
    nizke = check_nizke_zasoby()
    if not nizke:
        tg_send("✅ <b>SA: Týdenní check</b>\n\nVšechny zásoby jsou v pořádku 👍")
        return

    tg_send(
        f"📋 <b>SA: Týdenní check zásob</b>\n\n"
        f"Nalezeno {len(nizke)} materiálů vyžadujících pozornost:"
    )

    for m in nizke:
        cena_celkem = m["objednat_ks"] * m["cena_kc"]
        obj_id = uloz_objednavku(m["id"], m["objednat_ks"], cena_celkem, m["dodavatel_id"])
        posli_upozorneni_material(m, obj_id)
        time.sleep(0.5)  # Nezahlcuj Telegram API


def scheduler_loop():
    """Jednoduchý scheduler — spouští check každé pondělí v 8:00."""
    import zoneinfo
    while True:
        try:
            tz = zoneinfo.ZoneInfo("Europe/Prague")
            now = datetime.now(tz)
            if now.weekday() == 0 and now.hour == 8 and now.minute == 0:
                tydenni_check()
                time.sleep(61)  # Počkej minutu, aby se nespustil dvakrát
        except Exception as e:
            print(f"[SA Scheduler ERROR] {e}")
        time.sleep(30)


# ─────────────────────────────────────────────
# TELEGRAM WEBHOOK / POLLING
# ─────────────────────────────────────────────
_last_update_id = 0


def poll_telegram():
    """Long-polling pro Telegram zprávy a callback queries."""
    global _last_update_id
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"timeout": 20, "offset": _last_update_id + 1}
            r = requests.get(url, params=params, timeout=25)
            data = r.json()

            if not data.get("ok"):
                time.sleep(5)
                continue

            for update in data.get("result", []):
                _last_update_id = update["update_id"]
                zpracuj_update(update)

        except Exception as e:
            print(f"[SA Telegram Poll ERROR] {e}")
            time.sleep(5)


def zpracuj_update(update: dict):
    """Zpracuje příchozí Telegram zprávu nebo callback."""
    # Callback query (tlačítka)
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq.get("data", "")
        cq_id = cq["id"]
        chat_id = str(cq["message"]["chat"]["id"])
        message_id = cq["message"]["message_id"]

        if data.startswith("sa_schvalit_"):
            obj_id = int(data.split("_")[2])
            obj = schval_objednavku(obj_id)
            if obj:
                tg_answer_callback(cq_id, "✅ Schváleno!")
                tg_edit_message(
                    chat_id, message_id,
                    f"✅ <b>Objednávka schválena</b>\n"
                    f"{obj['nazev']} — {obj['mnozstvi']} {obj['jednotka']}\n"
                    f"Cena: {obj['cena_celkem']:.0f} Kč\n"
                    f"📧 Objednávka připravena k odeslání dodavateli."
                )
                # TODO SA-2: automaticky odeslat email dodavateli
            else:
                tg_answer_callback(cq_id, "Objednávka nenalezena")

        elif data.startswith("sa_odlozit_"):
            parts = data.split("_")
            obj_id = int(parts[2])
            dny = int(parts[3]) if len(parts) > 3 else 3
            zamitni_objednavku(obj_id, dny)
            tg_answer_callback(cq_id, f"⏰ Odloženo o {dny} dny")
            tg_edit_message(
                chat_id, message_id,
                f"⏰ Objednávka odložena o {dny} dny."
            )

        elif data.startswith("sa_zamitit_"):
            obj_id = int(data.split("_")[2])
            zamitni_objednavku(obj_id, 99)
            tg_answer_callback(cq_id, "❌ Zamítnuto")
            tg_edit_message(chat_id, message_id, "❌ Objednávka zamítnuta.")

        # ── User management callbacky ──
        elif data.startswith("user_schval_"):
            parts = data.split("_")
            novy_chat_id = parts[2]
            role = parts[3] if len(parts) > 3 else "assistant"
            # Pouze owner smí schvalovat
            if not ma_pravo(chat_id, "users_manage"):
                tg_answer_callback(cq_id, "⛔ Nemáš oprávnění")
                return
            ok = schval_uzivatele(novy_chat_id, role)
            if ok:
                tg_answer_callback(cq_id, "✅ Uživatel schválen")
                tg_edit_message(chat_id, message_id,
                    f"✅ Přístup schválen — role: <b>{role}</b>")
                tg_send(text_vitejte("", role), chat_id=novy_chat_id)
            else:
                tg_answer_callback(cq_id, "Uživatel nenalezen")

        elif data.startswith("user_zamit_"):
            novy_chat_id = data.split("_")[2]
            if not ma_pravo(chat_id, "users_manage"):
                tg_answer_callback(cq_id, "⛔ Nemáš oprávnění")
                return
            zamitni_uzivatele(novy_chat_id)
            tg_answer_callback(cq_id, "❌ Zamítnuto")
            tg_edit_message(chat_id, message_id, f"❌ Přístup zamítnut.")
            tg_send(text_pristup_odmitnuto(), chat_id=novy_chat_id)

    # Textová zpráva
    elif "message" in update:
        msg = update["message"]
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "").strip()

        if not text:
            return

        # ── /start — registrace nového uživatele ──
        if text.lower() == "/start":
            user = get_user(chat_id)
            if user and user.get("aktivni"):
                tg_send(f"👋 Ahoj <b>{user['jmeno']}</b>! SA Agent je připraven.\n/sklad — stav zásob\n/inventura — zadat zásoby", chat_id=chat_id)
            elif user and not user.get("aktivni"):
                tg_send("⏳ Tvoje žádost čeká na schválení doktorem.", chat_id=chat_id)
            else:
                # Neznámý uživatel — zaregistruj jako pending a notifikuj ownera
                from_user = msg.get("from", {})
                jmeno = f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip() or "Neznámý"
                registruj_pending(chat_id, jmeno)
                tg_send("⏳ Tvoje žádost byla odeslána doktorovi. Vyčkej na schválení.", chat_id=chat_id)
                # Notifikuj ownera
                cfg = get_config()
                owner = get_owner(cfg)
                if owner:
                    ordinace = cfg.get("ordinace", "ordinace")
                    zprava, keyboard = text_zadost_o_pristup(chat_id, jmeno, ordinace)
                    tg_send(zprava, reply_markup=keyboard, chat_id=owner["chat_id"])
            return

        # ── Autorizace pro všechny ostatní příkazy ──
        user = get_user(chat_id)
        if not user or not user.get("aktivni"):
            tg_send(text_neznam_uzivatele(), chat_id=chat_id)
            return

        prikaz = text.split()[0].lower() if text.startswith("/") else None

        # Příkazy SA
        if text.lower() in ["/sklad", "/sa", "sklad"]:
            zasoby = get_vsechny_zasob()
            odpovedni = zpracuj_telegram_prikaz("/sklad — zobraz stav všech zásob", zasoby)
            tg_send(f"📦 <b>SA: Stav skladu</b>\n\n{odpovedni}")

        elif text.lower().startswith("/pridat ") or text.lower().startswith("pridat "):
            # Formát: /pridat Supracain 40
            parts = text.split()
            if len(parts) >= 3:
                material_jmeno = " ".join(parts[1:-1])
                try:
                    mnozstvi = float(parts[-1])
                    zasoby = get_vsechny_zasob()
                    # Najdi materiál podle jména
                    nalezeny = next(
                        (m for m in zasoby if material_jmeno.lower() in m["nazev"].lower()),
                        None
                    )
                    if nalezeny:
                        pridat_dodavku(nalezeny["id"], mnozstvi, "ruční zápis Telegram")
                        tg_send(
                            f"✅ Přidáno: <b>{mnozstvi} {nalezeny['jednotka']}</b> "
                            f"— {nalezeny['nazev']}\n"
                            f"Nová zásoba: <b>{nalezeny['zasoba'] + mnozstvi}</b>"
                        )
                    else:
                        tg_send(f"❓ Materiál '{material_jmeno}' nenalezen ve skladu.")
                except ValueError:
                    tg_send("⚠️ Formát: /pridat [název] [množství]")

        elif text.lower().startswith("/spotreba ") or text.lower().startswith("spotřeba "):
            parts = text.split()
            if len(parts) >= 3:
                material_jmeno = " ".join(parts[1:-1])
                try:
                    mnozstvi = float(parts[-1])
                    zasoby = get_vsechny_zasob()
                    nalezeny = next(
                        (m for m in zasoby if material_jmeno.lower() in m["nazev"].lower()),
                        None
                    )
                    if nalezeny:
                        pridat_spotreba(nalezeny["id"], mnozstvi, "ruční zápis")
                        nova = max(0, nalezeny["zasoba"] - mnozstvi)
                        tg_send(
                            f"📉 Spotřeba: <b>{mnozstvi} {nalezeny['jednotka']}</b> "
                            f"— {nalezeny['nazev']}\n"
                            f"Zbývá: <b>{nova}</b>"
                        )
                    else:
                        tg_send(f"❓ Materiál '{material_jmeno}' nenalezen.")
                except ValueError:
                    tg_send("⚠️ Formát: /spotreba [název] [množství]")

        elif text.lower() == "/check":
            tydenni_check()

        else:
            # Volný text — Buddy odpovídá
            zasoby = get_vsechny_zasob()
            odpoved = zpracuj_telegram_prikaz(text, zasoby)
            tg_send(f"🤖 <b>SA Agent:</b>\n\n{odpoved}")


# ─────────────────────────────────────────────
# FastAPI ENDPOINTY
# ─────────────────────────────────────────────

class ZasobaUpdate(BaseModel):
    material_id: str
    zasoba: float
    poznamka: Optional[str] = ""


class SpotrebovaUpdate(BaseModel):
    material_id: str
    mnozstvi: float
    poznamka: Optional[str] = ""


@app.get("/")
def root():
    return {"status": "SA Agent běží", "version": "1.0.0"}


@app.get("/zdravi")
def zdravi():
    return {"ok": True, "agent": "SA", "cas": datetime.now().isoformat()}


@app.get("/sklad")
def get_sklad():
    """Vrátí kompletní stav skladu."""
    zasoby = get_vsechny_zasob()
    return {"materialy": zasoby, "celkem": len(zasoby)}


@app.get("/sklad/upozorneni")
def get_upozorneni():
    """Vrátí materiály pod minimem nebo blížící se minimu."""
    nizke = check_nizke_zasoby()
    return {"upozorneni": nizke, "pocet": len(nizke)}


@app.post("/sklad/update")
def post_update_zasoba(data: ZasobaUpdate):
    ok = update_zasoba(data.material_id, data.zasoba, data.poznamka)
    if not ok:
        raise HTTPException(404, f"Materiál {data.material_id} nenalezen")
    return {"ok": True}


@app.post("/sklad/spotreba")
def post_spotreba(data: SpotrebovaUpdate):
    ok = pridat_spotreba(data.material_id, data.mnozstvi, data.poznamka)
    if not ok:
        raise HTTPException(404, f"Materiál {data.material_id} nenalezen")
    return {"ok": True}


@app.post("/sklad/dodavka")
def post_dodavka(data: SpotrebovaUpdate):
    ok = pridat_dodavku(data.material_id, data.mnozstvi, data.poznamka)
    if not ok:
        raise HTTPException(404, f"Materiál {data.material_id} nenalezen")
    return {"ok": True}


@app.post("/check")
def manual_check():
    """Manuálně spustí týdenní check zásoby."""
    tydenni_check()
    return {"ok": True, "zprava": "Check spuštěn"}


# ─────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_db()
    print("✅ SA Agent: DB inicializována")

    if TELEGRAM_BOT_TOKEN:
        # Telegram polling ve vlákně
        t_poll = threading.Thread(target=poll_telegram, daemon=True)
        t_poll.start()
        print("✅ SA Agent: Telegram polling spuštěn")

    # Scheduler ve vlákně
    t_sched = threading.Thread(target=scheduler_loop, daemon=True)
    t_sched.start()
    print("✅ SA Agent: Scheduler spuštěn (check každé pondělí 8:00)")

    tg_send("🚀 <b>SA Agent spuštěn</b>\nSkladový a nákupní agent je online.\nPříkazy: /sklad /pridat /spotreba /check")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
