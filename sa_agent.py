"""
DentVantage SA Agent — AI mozek
Buddy prompt + analýza zásoby + návrhy objednávek
"""

import os
import json
import anthropic
from typing import List, Optional
from sklad import get_config, get_vsechny_zasob, predikuj_dny_do_dochazeni

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SA_SYSTEM_PROMPT = """Jsi SA Agent — specializovaný AI agent pro správu zásob a optimalizaci nákupů v zubní ordinaci MUDr. Pavla Vachulky v Českých Budějovicích.

Funguješ jako součást ekosystému DentVantage pod orchestrací Buddy.

Tvoje primární funkce:
- Analyzuješ aktuální stav zásob materiálů
- Predikuješ kdy který materiál dojde na základě spotřeby
- Upozorňuješ na blížící se expirace a nízké zásoby
- Navrhuješ nákupní objednávky ke schválení doktorem přes Telegram
- Pokud deteкuješ zdražení o >10%, signalizuješ to FA Agentovi

Kategorie materiálů:
- Anestetika (Supracain, Ubistesin)
- Výplňový materiál (kompozita, Bulk Fill)
- Endodontické materiály (sealery, CaOH)
- Chirurgické a augmentační materiály
- Implantologické komponenty

Komunikační styl:
- Píšeš stručně a konkrétně — doktor nemá čas
- Čísla vždy zaokrouhluješ na celé kusy nebo 1 desetinné místo
- Nikdy neobjednáváš bez schválení doktora
- Navrhneš optimální množství podle spotřeby (zásoba na 4-6 týdnů)

Odpovídáš VŽDY česky. Jsi přesný, praktický, spolehlivý."""


def formatuj_stav_skladu(zasoby: list) -> str:
    """Připraví přehled skladu pro Buddyho analýzu."""
    cfg = get_config()
    lines = []
    for m in zasoby:
        dny = predikuj_dny_do_dochazeni(m)
        dny_str = f"{dny} dní" if dny is not None else "neznámo"
        stav = "🔴 KRITICKÉ" if m["zasoba"] < m["minimum"] else (
            "🟡 POZOR" if dny is not None and dny <= 7 else "🟢 OK"
        )
        lines.append(
            f"{stav} {m['nazev']}: {m['zasoba']} {m['jednotka']} "
            f"(min. {m['minimum']}, dojde za {dny_str})"
        )
    return "\n".join(lines)


def navrhni_objednavky(zasoby_pod_minimem: list) -> str:
    """Buddy navrhne text objednávky pro Telegram zprávu."""
    if not zasoby_pod_minimem:
        return "Všechny zásoby jsou v pořádku."

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    cfg = get_config()
    stav_text = formatuj_stav_skladu(zasoby_pod_minimem)

    user_msg = f"""Aktuální stav zásob vyžadující pozornost:

{stav_text}

Pro každý materiál navrhni:
1. Množství k objednání (zásoba na 5 týdnů)
2. Prioritu (URGENTNÍ = dojde do 3 dní / BĚŽNÁ)
3. Odhadovanou cenu celkem v Kč

Odpověz stručně — výstup jde přímo do Telegram zprávy doktorovi."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=600,
        system=SA_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}]
    )

    return response.content[0].text


def zpracuj_telegram_prikaz(zprava: str, zasoby: list) -> str:
    """
    Buddy odpovídá na volný text od doktora přes Telegram.
    Např. '/sklad' nebo 'Supracain docházejí, mám asi 5'
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    stav_text = formatuj_stav_skladu(zasoby)

    user_msg = f"""Doktor napsal: "{zprava}"

Aktuální stav skladu:
{stav_text}

Pokud doktor hlásí stav konkrétního materiálu, potvrď zápis a poznamenej.
Pokud se ptá na stav skladu, shrň přehledně.
Pokud žádá o objednávku, navrhni ji s cenou.
Odpověz stručně, maximálně 5 řádků."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=400,
        system=SA_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}]
    )

    return response.content[0].text


def fa_signal_text(material: dict, zdrazeni_pct: float) -> str:
    """Připraví FA signal pro zdražení materiálu."""
    return (
        f"⚠️ FA SIGNAL: {material['nazev']} zdražil o {zdrazeni_pct}% "
        f"(nová cena: {material.get('cena_kc', '?')} Kč/{material.get('jednotka', 'ks')}). "
        f"Přepočítej marže dotčených výkonů."
    )
