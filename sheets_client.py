import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SHEET_ID = "1a2fmc8DKCjYugNiZHJ5aM508lC9k53IoDwsLhplRlc8"

DEFAULT_FC_MAX = 187

DEFAULT_ZONE_SPECS = {
    "Z1": {"label": "Récupération", "short_label": "Récupération", "min_pct": 50.0, "max_pct": 60.0},
    "Z2": {"label": "Endurance Fondamentale", "short_label": "Endurance Fond.", "min_pct": 60.0, "max_pct": 75.0},
    "Z3": {"label": "Tempo / Aérobie", "short_label": "Tempo / Aérobie", "min_pct": 75.0, "max_pct": 85.0},
    "Z4": {"label": "Seuil", "short_label": "Seuil", "min_pct": 85.0, "max_pct": 92.0},
    "Z5": {"label": "PMA / Anaérobie", "short_label": "PMA / Max", "min_pct": 92.0, "max_pct": 100.0},
}


def round_bpm(val):
    """Arrondi standard (demi-supérieur) en bpm entier."""
    return int(float(val) + 0.5)


def _parse_float(val):
    """Convertit une cellule Google Sheet (virgule FR, %, espaces) en float, ou None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none", ""}:
        return None
    s = (
        s.replace("\u00a0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace("%", "")
        .replace("bpm", "")
        .replace("BPM", "")
        .replace(",", ".")
    )
    try:
        return float(s)
    except ValueError:
        return None


def _parse_pct(val):
    """Parse un pourcentage (accepte 92, '92%', ou 0.92)."""
    num = _parse_float(val)
    if num is None:
        return None
    if 0 < num <= 1.0:
        return round(num * 100.0, 2)
    return num


def _format_pct(val):
    """Formate un pourcentage sans '.0' inutile."""
    f = float(val)
    return str(int(round(f))) if abs(f - round(f)) < 1e-6 else f"{f:g}"


def build_default_fc_config(fc_max=DEFAULT_FC_MAX, source="Valeurs par défaut"):
    """Construit une configuration de zones cardiaques complète à partir d'une FC max."""
    fc_val = float(fc_max)
    zones = {}
    for z_key, spec in DEFAULT_ZONE_SPECS.items():
        zones[z_key] = {
            "label": spec["label"],
            "short_label": spec["short_label"],
            "min_pct": spec["min_pct"],
            "max_pct": spec["max_pct"],
            "min_bpm": round(fc_val * spec["min_pct"] / 100.0, 2),
            "max_bpm": round(fc_val * spec["max_pct"] / 100.0, 2),
        }
    return {
        "fc_max": round_bpm(fc_val),
        "fc_max_raw": fc_val,
        "source": source,
        "zones": zones,
    }


def parse_fc_max_values(rows, source="Google Sheet (onglet FC_max)"):
    """
    Parse les lignes brutes (get_all_values) de l'onglet FC_max.
    Format attendu :
      Ligne 1 : A1='Freq max', B1=187
      Ligne 3 : Min % | Max % | Min | Max
      Lignes suivantes : Z5..Z1 (ou Z1..Z5) avec Min %, Max %, Min, Max
    """
    if not rows:
        return build_default_fc_config(source=f"Valeurs par défaut ({source} vide)")

    fc_max_val = None
    col_min_pct, col_max_pct, col_min_bpm, col_max_bpm = 1, 2, 3, 4

    # 1. Recherche de la FC max et des colonnes d'en-tête éventuelles
    for idx_r, row in enumerate(rows):
        if not row:
            continue
        c0 = str(row[0]).strip().lower()
        c0_norm = c0.replace("é", "e").replace("è", "e").replace("_", " ").strip()
        if any(tok in c0_norm for tok in ("freq max", "frequence max", "fc max", "fcmax")):
            if len(row) > 1:
                parsed = _parse_float(row[1])
                if parsed and 80 <= parsed <= 250:
                    fc_max_val = parsed

        # Détection de la ligne d'en-têtes des zones (Min %, Max %, Min, Max)
        row_lower = [str(c).strip().lower() for c in row]
        if any("min %" in c or "min%" in c for c in row_lower) and any("max %" in c or "max%" in c for c in row_lower):
            for c_idx, cell_txt in enumerate(row_lower):
                if "min %" in cell_txt or "min%" in cell_txt:
                    col_min_pct = c_idx
                elif "max %" in cell_txt or "max%" in cell_txt:
                    col_max_pct = c_idx
                elif cell_txt == "min":
                    col_min_bpm = c_idx
                elif cell_txt == "max":
                    col_max_bpm = c_idx

    # Fallback B1 si le libellé A1 a été renommé
    if fc_max_val is None and len(rows) > 0 and len(rows[0]) > 1:
        b1 = _parse_float(rows[0][1])
        if b1 and 80 <= b1 <= 250:
            fc_max_val = b1

    # 2. Lecture des lignes Z1..Z5
    parsed_zones = {}
    for row in rows:
        if not row:
            continue
        z_raw = str(row[0]).strip().upper()
        z_key = z_raw[:2] if len(z_raw) >= 2 and z_raw[:2] in DEFAULT_ZONE_SPECS else None
        if not z_key:
            continue

        def _get_cell(col_i):
            return row[col_i] if col_i < len(row) else None

        parsed_zones[z_key] = {
            "min_pct": _parse_pct(_get_cell(col_min_pct)),
            "max_pct": _parse_pct(_get_cell(col_max_pct)),
            "min_bpm": _parse_float(_get_cell(col_min_bpm)),
            "max_bpm": _parse_float(_get_cell(col_max_bpm)),
        }

    # Si FC max absente en B1 mais Z5 Max présente, on s'en sert
    if fc_max_val is None:
        z5_max = parsed_zones.get("Z5", {}).get("max_bpm")
        if z5_max and 80 <= z5_max <= 250:
            fc_max_val = z5_max
        else:
            fc_max_val = float(DEFAULT_FC_MAX)

    # 3. Assemblage propre Z1 -> Z5 avec calcul de secours si une cellule manque
    zones = {}
    for z_key, spec in DEFAULT_ZONE_SPECS.items():
        pz = parsed_zones.get(z_key, {})
        min_pct = pz.get("min_pct") if pz.get("min_pct") is not None else spec["min_pct"]
        max_pct = pz.get("max_pct") if pz.get("max_pct") is not None else spec["max_pct"]
        min_bpm = pz.get("min_bpm") if pz.get("min_bpm") is not None else round(fc_max_val * min_pct / 100.0, 2)
        max_bpm = pz.get("max_bpm") if pz.get("max_bpm") is not None else round(fc_max_val * max_pct / 100.0, 2)
        zones[z_key] = {
            "label": spec["label"],
            "short_label": spec["short_label"],
            "min_pct": min_pct,
            "max_pct": max_pct,
            "min_bpm": min_bpm,
            "max_bpm": max_bpm,
        }

    return {
        "fc_max": round_bpm(fc_max_val),
        "fc_max_raw": float(fc_max_val),
        "source": source,
        "zones": zones,
    }


def load_fc_config(sh):
    """Lit la FC max et les 5 zones cardiaques depuis l'onglet 'FC_max' du Google Sheet."""
    if sh is None:
        return build_default_fc_config(source="Valeurs par défaut (Sheet non connecté)")
    try:
        ws = None
        try:
            ws = sh.worksheet("FC_max")
        except gspread.exceptions.WorksheetNotFound:
            for candidate in sh.worksheets():
                title_norm = candidate.title.strip().lower().replace(" ", "_")
                if title_norm in {"fc_max", "fcmax", "freq_max", "frequence_max"}:
                    ws = candidate
                    break
        if ws is None:
            return build_default_fc_config(source="Valeurs par défaut (onglet FC_max introuvable)")

        rows = ws.get_all_values()
        return parse_fc_max_values(rows, source=f"Google Sheet (onglet {ws.title})")
    except Exception as e:
        return build_default_fc_config(source=f"Valeurs par défaut (erreur lecture FC_max : {e})")


def format_zones_fc_texte(fc_config):
    """Génère le bloc texte des 5 zones cardiaques pour les prompts IA."""
    zones = (fc_config or build_default_fc_config())["zones"]
    lignes = []
    for z_key in ("Z1", "Z2", "Z3", "Z4", "Z5"):
        z = zones[z_key]
        p_min = _format_pct(z["min_pct"])
        p_max = _format_pct(z["max_pct"])
        b_min = round_bpm(z["min_bpm"])
        b_max = round_bpm(z["max_bpm"])
        lignes.append(f"- {z_key} ({z['label']} : {p_min}-{p_max}%) : {b_min} - {b_max} bpm")
    return "\n" + "\n".join(lignes) + "\n"


def connect_to_sheets():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        
        active_id = st.secrets.get("SHEET_ID", SHEET_ID)
        return gc.open_by_key(active_id)
        
    except Exception as e:
        st.error(f"Impossible de se connecter à la base de données : {e}")
        return None