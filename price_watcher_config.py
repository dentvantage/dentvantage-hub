"""
DentVantage SA Agent — Price Watcher v1
Sledování cen napříč dentálními e-shopy
"""

# ═══════════════════════════════════════════════════════════
# KATALOG E-SHOPŮ
# ═══════════════════════════════════════════════════════════
#
# Rozdělení podle přístupu k cenám:
#
# TYP A — veřejné ceny (scraping bez přihlášení)
# TYP B — ceny až po přihlášení (nutné credentials)
# TYP C — na dotaz / individuální nabídka (nelze scraping)
#
# ───────────────────────────────────────────────────────────

ESHOPY = {

    # ── TYP A: VEŘEJNÉ CENY ────────────────────────────────

    "hdtdental": {
        "nazev": "HDT Dental",
        "url": "https://www.hdtdental.cz",
        "typ": "A",
        "platform": "shoptet",
        "silne_stranky": ["Dentsply Sirona", "WaveOne", "ProTaper", "LM Dental", "W&H"],
        "akce_url": "https://www.hdtdental.cz/slevy/",
        "expirace_url": "https://www.hdtdental.cz/expirace-2026/",
        "scraping": "html_requests",
        "poznamka": "Ceny viditelné bez přihlášení. Akce sekce veřejná.",
    },
    "odonto": {
        "nazev": "Odonto.cz",
        "url": "https://www.odonto.cz",
        "typ": "A",
        "platform": "custom",
        "silne_stranky": ["Kerr", "GC", "Edenta", "Chirurgie", "Rotační nástroje"],
        "akce_url": "https://www.odonto.cz/filtr/akcni-nabidky/",
        "vyprodej_url": "https://www.odonto.cz/filtr/vyprodej/",
        "scraping": "html_requests",
        "poznamka": "Veřejné ceny. Sekce Akce + Výprodej + Produkty s kratší expirací.",
    },
    "hsdental": {
        "nazev": "HS Dental Shop",
        "url": "https://hsdental-shop.cz",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["různé"],
        "scraping": "html_requests",
        "poznamka": "Ověřit při prvním scrapingu.",
    },
    "topdent": {
        "nazev": "Top-Dent",
        "url": "https://www.top-dent.cz",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["různé"],
        "scraping": "html_requests",
        "poznamka": "Ověřit při prvním scrapingu.",
    },
    "tokuyama": {
        "nazev": "Tokuyama Dental EU",
        "url": "https://tokuyama-dental.eu/cz/shop/",
        "typ": "A",
        "platform": "woocommerce",
        "silne_stranky": ["Tokuyama kompozita", "Estelite", "bonding"],
        "scraping": "html_requests",
        "poznamka": "WooCommerce — dobře scrapovatelný.",
    },
    "hufa": {
        "nazev": "Hufa",
        "url": "https://www.hufa.cz",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["různé"],
        "scraping": "html_requests",
        "poznamka": "Ověřit při prvním scrapingu.",
    },
    "smrcek": {
        "nazev": "Šmrček Dental",
        "url": "https://eshop.smrcek-dental.cz",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["různé"],
        "akce_url": "https://eshop.smrcek-dental.cz/kategorie/-ordinace/",
        "scraping": "html_requests",
        "poznamka": "Ověřit při prvním scrapingu.",
    },
    "janda": {
        "nazev": "Janda Dental",
        "url": "https://www.janda-dental.cz",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["různé"],
        "scraping": "html_requests",
        "poznamka": "Ověřit při prvním scrapingu.",
    },
    "italdent": {
        "nazev": "Ital Dent",
        "url": "https://www.italdent.cz",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["italské výrobky"],
        "akce_url": "https://www.italdent.cz/2-stomatologie/",
        "scraping": "html_requests",
        "poznamka": "Ověřit při prvním scrapingu.",
    },
    "rodentica": {
        "nazev": "Rodentica",
        "url": "https://eshop.rodentica.eu",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["různé"],
        "scraping": "html_requests",
        "poznamka": "Ověřit při prvním scrapingu.",
    },
    "dentalordinace": {
        "nazev": "Dental-Ordinace",
        "url": "https://www.dental-ordinace.cz",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["různé"],
        "scraping": "html_requests",
        "poznamka": "Ověřit při prvním scrapingu.",
    },
    "fenixdental": {
        "nazev": "Fenix Dental",
        "url": "https://www.fenixdental.cz",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["různé"],
        "scraping": "html_requests",
        "poznamka": "Ověřit při prvním scrapingu.",
    },
    "mwdental": {
        "nazev": "MW Dental",
        "url": "http://www.mwdental.cz",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["M+W produkty"],
        "scraping": "html_requests",
        "poznamka": "HTTP (ne HTTPS) — opatrně. Ověřit.",
    },
    "dentall": {
        "nazev": "Dentall",
        "url": "https://www.dentall.cz",
        "typ": "A",
        "platform": "neznamy",
        "silne_stranky": ["různé"],
        "scraping": "html_requests",
        "poznamka": "Ověřit při prvním scrapingu.",
    },

    # ── TYP B: PŘIHLÁŠENÍ NUTNÉ ────────────────────────────

    "dentamed": {
        "nazev": "Dentamed",
        "url": "https://www.dentamed.cz",
        "typ": "B",
        "platform": "custom",
        "silne_stranky": ["GC", "Ivoclar", "bonding", "výplně", "spotřební"],
        "login_url": "https://www.dentamed.cz/login",
        "env_user": "DENTAMED_USER",
        "env_pass": "DENTAMED_PASS",
        "poznamka": "Individuální slevy 23–47%. Nutné přihlášení pro reálné ceny.",
    },

    # ── TYP C: NA DOTAZ / NELZE SCRAPING ──────────────────

    "janouch": {
        "nazev": "Janouch Dental",
        "url": "https://www.janouch-dental.cz",
        "typ": "C",
        "silne_stranky": ["různé"],
        "poznamka": "Ověřit — možná jen katalog bez cen.",
    },
}

# ═══════════════════════════════════════════════════════════
# PRICE WATCHER — LOGIKA (SA-3 fáze)
# ═══════════════════════════════════════════════════════════
#
# Pro každý materiál v sa_config.json:
# 1. Vezmi název + kat. číslo
# 2. Prohledej relevantní e-shopy (dle kategorie)
# 3. Porovnej s poslední zaznamenanou cenou v DB
# 4. Pokud pokles > 5% → ulož + notifikuj
# 5. Pokud nárůst > 10% → FA signal
#
# Mapování kategorií → e-shopy (priorita):
KATEGORIE_ESHOPY = {
    "endodoncie":      ["hdtdental", "odonto", "hsdental", "smrcek"],
    "vylnovy_material":["dentamed", "tokuyama", "odonto", "italdent"],
    "bonding":         ["dentamed", "tokuyama", "hdtdental"],
    "cementy":         ["dentamed", "odonto", "janda"],
    "protetika":       ["dentamed", "odonto", "rodentica"],
    "chirurgie":       ["odonto", "hsdental", "fenixdental"],
    "spotrebni":       ["dentamed", "odonto", "mwdental", "dentall"],
    "dezinfekce":      ["dentamed", "hdtdental", "hufa"],
    "anestetika":      ["dentamed", "hsdental", "topdent"],
    "rotacni_nastroje":["hdtdental", "odonto", "smrcek"],
    "implantaty":      ["odonto"],  # INNO zatím jen přímý dodavatel Cowellmedi
}

# ═══════════════════════════════════════════════════════════
# SCRAPING STRATEGIE
# ═══════════════════════════════════════════════════════════
#
# Fáze 1 (SA-3a): AKCE + VÝPRODEJ stránky
#   → Každý pondělí — projdi akce URL všech e-shopů
#   → Hledej produkty které máme v sa_config.json
#   → Match podle názvu (fuzzy) nebo kat. čísla
#
# Fáze 2 (SA-3b): PŘÍMÉ VYHLEDÁVÁNÍ
#   → Pro každý materiál v sa_config.json
#   → Hledej na e-shopu podle názvu
#   → Ulož nalezené ceny do ceny_historie
#
# Fáze 3 (SA-3c): PŘIHLÁŠENÍ (Dentamed)
#   → Selenium nebo requests.Session
#   → Login → stáhnout osobní ceník
#   → Porovnat s aktuálními cenami v DB
#
# POZOR na rate limiting:
#   → Mezi requesty sleep(2-5s)
#   → Max 1 scraping session / e-shop / den
#   → User-Agent: Mozilla/5.0 ...
#   → Respektovat robots.txt

if __name__ == "__main__":
    print(f"Celkem e-shopů: {len(ESHOPY)}")
    typ_a = [k for k,v in ESHOPY.items() if v['typ']=='A']
    typ_b = [k for k,v in ESHOPY.items() if v['typ']=='B']
    typ_c = [k for k,v in ESHOPY.items() if v['typ']=='C']
    print(f"  Typ A (veřejné ceny): {len(typ_a)} — {', '.join(typ_a)}")
    print(f"  Typ B (přihlášení):   {len(typ_b)} — {', '.join(typ_b)}")
    print(f"  Typ C (na dotaz):     {len(typ_c)} — {', '.join(typ_c)}")
