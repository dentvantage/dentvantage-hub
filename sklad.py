"""
DentVantage SA Agent — Sklad modul
Správa zásob: SQLite CRUD, predikce, FA signal
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict

DB_PATH = os.environ.get("SA_DB_PATH", "sklad.db")
CONFIG_PATH = os.environ.get("SA_CONFIG_PATH", "sa_config.json")


def get_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Inicializuje DB tabulky."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS zasoba (
            id TEXT PRIMARY KEY,
            nazev TEXT NOT NULL,
            kategorie TEXT,
            jednotka TEXT,
            zasoba REAL DEFAULT 0,
            minimum REAL DEFAULT 0,
            objednat_ks REAL DEFAULT 0,
            spotreba_tyden REAL DEFAULT 0,
            dodavatel_id TEXT,
            cena_kc REAL DEFAULT 0,
            kat_cislo TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS pohyby (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id TEXT NOT NULL,
            typ TEXT NOT NULL,
            mnozstvi REAL NOT NULL,
            poznamka TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS objednavky (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id TEXT NOT NULL,
            mnozstvi REAL NOT NULL,
            cena_celkem REAL,
            dodavatel_id TEXT,
            stav TEXT DEFAULT 'ceka',
            schvaleno_at TEXT,
            odeslano_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ceny_historie (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id TEXT NOT NULL,
            cena_kc REAL NOT NULL,
            dodavatel_id TEXT,
            recorded_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    # Načti materiály z config.json do DB (pokud ještě nejsou)
    cfg = get_config()
    for m in cfg["sa"]["materialy"]:
        existing = conn.execute(
            "SELECT id FROM zasoba WHERE id = ?", (m["id"],)
        ).fetchone()
        if not existing:
            conn.execute("""
                INSERT INTO zasoba
                (id, nazev, kategorie, jednotka, zasoba, minimum, objednat_ks,
                 spotreba_tyden, dodavatel_id, cena_kc, kat_cislo, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                m["id"], m["nazev"], m.get("kategorie"), m.get("jednotka"),
                m.get("zasoba", 0), m.get("minimum", 0), m.get("objednat_ks", 0),
                m.get("spotreba_tyden", 0), m.get("dodavatel_id"), m.get("cena_kc", 0),
                m.get("kat_cislo_dodavatele"), datetime.utcnow().isoformat()
            ))
    conn.commit()
    conn.close()
    print("✅ SA: DB inicializována")


def get_vsechny_zasob() -> List[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM zasoba ORDER BY kategorie, nazev").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_material(material_id: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM zasoba WHERE id = ?", (material_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_zasoba(material_id: str, nova_zasoba: float, poznamka: str = "") -> bool:
    """Nastaví zásobu na konkrétní hodnotu (inventura)."""
    conn = get_db()
    old = conn.execute("SELECT zasoba FROM zasoba WHERE id = ?", (material_id,)).fetchone()
    if not old:
        conn.close()
        return False
    diff = nova_zasoba - old["zasoba"]
    typ = "inventura_plus" if diff >= 0 else "inventura_minus"
    conn.execute(
        "UPDATE zasoba SET zasoba = ?, updated_at = ? WHERE id = ?",
        (nova_zasoba, datetime.utcnow().isoformat(), material_id)
    )
    conn.execute(
        "INSERT INTO pohyby (material_id, typ, mnozstvi, poznamka) VALUES (?,?,?,?)",
        (material_id, typ, abs(diff), poznamka or "ruční úprava")
    )
    conn.commit()
    conn.close()
    return True


def pridat_spotreba(material_id: str, mnozstvi: float, poznamka: str = "") -> bool:
    """Odečte spotřebu od zásoby."""
    conn = get_db()
    row = conn.execute("SELECT zasoba FROM zasoba WHERE id = ?", (material_id,)).fetchone()
    if not row:
        conn.close()
        return False
    nova = max(0, row["zasoba"] - mnozstvi)
    conn.execute(
        "UPDATE zasoba SET zasoba = ?, updated_at = ? WHERE id = ?",
        (nova, datetime.utcnow().isoformat(), material_id)
    )
    conn.execute(
        "INSERT INTO pohyby (material_id, typ, mnozstvi, poznamka) VALUES (?,?,?,?)",
        (material_id, "spotreba", mnozstvi, poznamka)
    )
    conn.commit()
    conn.close()
    return True


def pridat_dodavku(material_id: str, mnozstvi: float, poznamka: str = "") -> bool:
    """Přičte dodávku k zásobě."""
    conn = get_db()
    row = conn.execute("SELECT zasoba FROM zasoba WHERE id = ?", (material_id,)).fetchone()
    if not row:
        conn.close()
        return False
    nova = row["zasoba"] + mnozstvi
    conn.execute(
        "UPDATE zasoba SET zasoba = ?, updated_at = ? WHERE id = ?",
        (nova, datetime.utcnow().isoformat(), material_id)
    )
    conn.execute(
        "INSERT INTO pohyby (material_id, typ, mnozstvi, poznamka) VALUES (?,?,?,?)",
        (material_id, "dodavka", mnozstvi, poznamka)
    )
    conn.commit()
    conn.close()
    return True


def predikuj_dny_do_dochazeni(material: dict) -> Optional[int]:
    """Odhadne počet dní do vyčerpání zásoby."""
    if material["spotreba_tyden"] and material["spotreba_tyden"] > 0:
        tyden_denni = material["spotreba_tyden"] / 5  # pracovní dny
        return int(material["zasoba"] / tyden_denni)
    return None


def check_nizke_zasoby() -> List[dict]:
    """Vrátí materiály pod minimem nebo blížící se minimu (do 7 dní)."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM zasoba").fetchall()
    conn.close()

    upozorneni = []
    for r in rows:
        m = dict(r)
        pod_minimem = m["zasoba"] < m["minimum"]
        dny = predikuj_dny_do_dochazeni(m)
        blizi_se = dny is not None and dny <= 7

        if pod_minimem or blizi_se:
            m["dny_do_dochazeni"] = dny
            m["pod_minimem"] = pod_minimem
            upozorneni.append(m)

    return upozorneni


def uloz_objednavku(material_id: str, mnozstvi: float, cena_celkem: float, dodavatel_id: str) -> int:
    """Uloží novou objednávku čekající na schválení. Vrací ID."""
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO objednavky (material_id, mnozstvi, cena_celkem, dodavatel_id, stav)
        VALUES (?,?,?,?,'ceka')
    """, (material_id, mnozstvi, cena_celkem, dodavatel_id))
    obj_id = cur.lastrowid
    conn.commit()
    conn.close()
    return obj_id


def schval_objednavku(obj_id: int) -> Optional[dict]:
    """Označí objednávku jako schválenou. Vrací detail pro odeslání."""
    conn = get_db()
    conn.execute(
        "UPDATE objednavky SET stav='schvalena', schvaleno_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), obj_id)
    )
    conn.commit()
    row = conn.execute("""
        SELECT o.*, z.nazev, z.kat_cislo, z.jednotka
        FROM objednavky o JOIN zasoba z ON o.material_id = z.id
        WHERE o.id = ?
    """, (obj_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def zamitni_objednavku(obj_id: int, dny: int = 3):
    """Odloží objednávku o N dní."""
    odlozit_do = (datetime.utcnow() + timedelta(days=dny)).isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE objednavky SET stav='odlozena', schvaleno_at=? WHERE id=?",
        (odlozit_do, obj_id)
    )
    conn.commit()
    conn.close()


def uloz_cenu(material_id: str, cena: float, dodavatel_id: str):
    """Zaznamená cenu do historie — pro detekci zdražení."""
    conn = get_db()
    conn.execute(
        "INSERT INTO ceny_historie (material_id, cena_kc, dodavatel_id) VALUES (?,?,?)",
        (material_id, cena, dodavatel_id)
    )
    conn.commit()
    conn.close()


def zkontroluj_zdrazeni(material_id: str, nova_cena: float, threshold_pct: float = 10.0) -> Optional[float]:
    """
    Porovná novou cenu s poslední zaznamenanou.
    Vrací % zdražení pokud přesáhne threshold, jinak None.
    """
    conn = get_db()
    row = conn.execute("""
        SELECT cena_kc FROM ceny_historie
        WHERE material_id = ?
        ORDER BY recorded_at DESC LIMIT 1
    """, (material_id,)).fetchone()
    conn.close()

    if not row:
        return None

    stara = row["cena_kc"]
    if stara <= 0:
        return None

    zmena_pct = (nova_cena - stara) / stara * 100
    if zmena_pct >= threshold_pct:
        return round(zmena_pct, 1)
    return None
