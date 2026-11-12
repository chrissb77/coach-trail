import streamlit as st
import pandas as pd
from google import genai
import importlib
import strava_client
importlib.reload(strava_client)
import sheets_client
import json
import time
import os
import requests
import streamlit.components.v1 as components
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px 

st.set_page_config(page_title="Coach Trail IA", page_icon="🏃‍♂️", layout="wide")

st.title("🏃‍♂️ Coach Virtuel - 60km")

# --- CONSTANTES PHYSIOLOGIQUES & LOGISTIQUES ---
ZONES_FC_TEXTE = """
- Z1 (Récupération : 50-60%) : 90 - 108 bpm
- Z2 (Endurance Fondamentale : 60-75%) : 108 - 135 bpm
- Z3 (Tempo / Aérobie : 75-85%) : 135 - 153 bpm
- Z4 (Seuil : 85-92%) : 153 - 166 bpm
- Z5 (PMA / Anaérobie : 92-100%) : 166 - 180 bpm
"""

REGLES_LOGISTIQUES_COACH = """
CATALOGUE DES OPTIONS LOGISTIQUES & MATÉRIEL DISPONIBLES :
1. Trajets Travail (à privilégier le VENDREDI) :
   - Option A "Vélotaf Route/Gravel" : Trajet retour à vélo en Z1/Z2 (108-135 bpm) pour accumuler du volume aérobie sans impact articulaire.
   - Option B "Retour du travail à pied (Run-commute Choc)" : 40 km avec 1000m D+ en Z2 (108-135 bpm). C'est une très grosse séance spécifique ultra qui remplace la sortie longue du week-end (à programmer uniquement lors des semaines de charge clé ou sur demande, suivie d'un week-end très allégé).
2. Option "VTT Électrique (VTTAE)" :
   - Disponible (au printemps ou le week end) pour des séances souples de récupération active en Z1 (90-108 bpm) ou d'endurance fondamentale Z2 basse (108-125 bpm). Idéal pour travailler la vélocité, profiter des sentiers en forêt sans faire monter le cardio dans les bosses, ou débloquer les jambes le dimanche veille de foot.

RÈGLES D'ORGANISATION HEBDOMADAIRE :
- LUNDI : Football (séance fixe, haute intensité cardio Z4/Z5 et forte charge excentrique/tendineuse).
- MARDI : Récupération post-foot (Repos, mobilité/renfo Achille, ou VTTAE très souple en Z1).
- VENDREDI : Jour privilégié pour les options au départ du travail (Vélotaf ou, ponctuellement, le retour à pied de 40km / 1000m D+).
- SAMEDI : Jour privilégié pour la Sortie Longue Trail (afin de garantir 48h de récupération avant le football du lundi), SAUF si le retour à pied de 40km a eu lieu le vendredi (auquel cas samedi = repos ou VTTAE Z1).
- DIMANCHE : Séance souple d'assimilation (VTTAE Z1/Z2, vélo souple, footing court Z2 ou repos) pour arriver frais au foot le lundi.
- CONSIGNE FORMAT : Chaque séance d'endurance DOIT mentionner la zone cible et les bpm (ex: "VTTAE souple 1h30 en Z1/Z2 (95-120 bpm)"). La colonne 'Focus' (3e colonne) doit contenir le thème de la semaine suivi de 2-3 phrases expliquant la logique physiologique et le choix des options retenues.
"""

# --- FONCTION UTILE : DÉTECTION DE LA SEMAINE EN COURS ---
def get_current_week_index(df_plan):
    try:
        today = datetime.now()
        mois_map = {
            "jan": 1, "fév": 2, "fev": 2, "mar": 3, "avr": 4, "mai": 5, "jui": 6,
            "juin": 6, "juil": 7, "aoû": 8, "aou": 8, "sep": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12
        }
        
        for idx, row in df_plan.iterrows():
            date_str = str(row.get('Date', ''))
            parts = date_str.split('-')
            if len(parts) == 2:
                s_parts = parts[0].strip().split()
                s_month = mois_map.get(s_parts[1].lower()[:3], today.month)
                d_start = datetime(today.year, s_month, int(s_parts[0]))
                
                e_parts = parts[1].strip().split()
                e_month = mois_map.get(e_parts[1].lower()[:3], today.month)
                d_end = datetime(today.year, e_month, int(e_parts[0]))
                
                if d_start > d_end:
                    d_end = d_end.replace(year=today.year + 1)
                
                if d_start <= today <= d_end.replace(hour=23, minute=59):
                    return idx
    except Exception:
        pass
    return len(df_plan) - 1 if not df_plan.empty else 0

# --- FONCTION D'AFFICHAGE D'UNE SEMAINE EN FLEXBOX ---
def render_week_card(row, is_current, jour_actuel, jours_fr):
    focus_texte = str(row.get('Focus', 'Non défini'))
    st.markdown(
        f"<div style='background-color: #f0f4f8; border-left: 4px solid #1f77b4; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px; font-size: 14px; color: #222;'>"
        f"🎯 <b>Logique & Objectif de la semaine :</b> {focus_texte}</div>",
        unsafe_allow_html=True
    )
    
    html_content = "<div style='display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px;'>"
    for jour in jours_fr:
        contenu = str(row.get(jour, "Repos")).replace('\n', '<br>')
        if is_current and jour == jour_actuel:
            border_color = "#4CAF50"
            bg_color = "#e8f5e9"
            titre_color = "#2e7d32"
        else:
            border_color = "#ddd"
            bg_color = "#ffffff"
            titre_color = "#333"
            
        html_content += (
            "<div style='flex: 1 1 12%; min-width: 130px; background-color: " + bg_color + 
            "; padding: 12px; border: 1px solid " + border_color + 
            "; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);'>"
            "<div style='color: " + titre_color + "; font-weight: bold; margin-bottom: 8px; border-bottom: 1px solid " + border_color + "; padding-bottom: 4px;'>" + jour + "</div>"
            "<div style='font-size: 14px; color: #555;'>" + contenu + "</div>"
            "</div>"
        )
    html_content += "</div>"
    st.write(html_content, unsafe_allow_html=True)

# --- VÉRIFICATION DISPONIBILITÉ MÉDIA RENFORCEMENT ---
@st.cache_data(ttl=300, show_spinner=False)
def verifier_disponibilite_media(media_url):
    if pd.isna(media_url):
        return "❌ Non renseigné"
    media_str = str(media_url).strip()
    if not media_str or media_str.lower() in ["nan", "none"]:
        return "❌ Non renseigné"
    if media_str.startswith(("http://", "https://")):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.head(media_str, allow_redirects=True, timeout=2.5, headers=headers)
            if r.status_code >= 400:
                r = requests.get(media_str, stream=True, timeout=2.5, headers=headers)
            return "✅ Disponible" if r.status_code < 400 else "❌ Introuvable (Web)"
        except Exception:
            return "❌ Introuvable (Web)"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.isfile(media_str) or os.path.isfile(os.path.join(base_dir, media_str)):
        return "✅ Disponible"
    return "❌ Fichier introuvable"

def extraire_tags_materiel(serie_materiel):
    """Extrait la liste triée des équipements uniques à partir d'une série pandas."""
    ignores = {"", "nan", "none", "aucun", "sans", "poids du corps", "non"}
    items = set()
    for val in serie_materiel.dropna().astype(str):
        for part in val.split(','):
            p = part.strip()
            if p.lower() not in ignores:
                items.add(p)
    return sorted(items)

def est_sans_materiel(val):
    if pd.isna(val):
        return True
    s = str(val).strip().lower()
    return s in {"", "nan", "none", "aucun", "sans", "poids du corps", "non"}

def est_unilateral(val):
    """Retourne True si la colonne Unilateral indique que l'exercice se fait sur chaque jambe / côté."""
    if pd.isna(val):
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in {"oui", "yes", "true", "1", "2", "g/d", "g+d", "jambe", "chaque jambe", "unilateral", "unilatéral", "par jambe"}

def deplier_exercices_unilateraux(df_seance):
    """Déplie chaque exercice marqué Chaque_Jambe / Unilateral en 2 étapes consécutives : Jambe Gauche puis Jambe Droite."""
    if df_seance is None or df_seance.empty:
        return pd.DataFrame()
    lignes_depliees = []
    for _, row in df_seance.iterrows():
        is_uni = bool(row.get('Chaque_Jambe', est_unilateral(row.get('Unilateral', ''))))
        if is_uni:
            r_gauche = row.copy()
            r_gauche['Nom_Base'] = str(row.get('Nom', ''))
            r_gauche['Nom'] = f"{row.get('Nom', '')} — 🦵 Jambe / Côté GAUCHE"
            lignes_depliees.append(r_gauche)

            r_droite = row.copy()
            r_droite['Nom_Base'] = str(row.get('Nom', ''))
            r_droite['Nom'] = f"{row.get('Nom', '')} — 🦵 Jambe / Côté DROIT"
            lignes_depliees.append(r_droite)
        else:
            r_norm = row.copy()
            r_norm['Nom_Base'] = str(row.get('Nom', ''))
            lignes_depliees.append(r_norm)
    return pd.DataFrame(lignes_depliees).reset_index(drop=True)

CATALOGUE_STRAVA_EXERCICES = [
    {"Catégorie": "Cuisses / Squats", "Strava_Exercise_Type": "SQUAT", "Exemples FR": "Squat classique, Air squat"},
    {"Catégorie": "Cuisses / Squats", "Strava_Exercise_Type": "GOBLET_SQUAT", "Exemples FR": "Squat gobelet (avec haltère/kettlebell)"},
    {"Catégorie": "Cuisses / Squats", "Strava_Exercise_Type": "BULGARIAN_SPLIT_SQUAT", "Exemples FR": "Squat bulgare"},
    {"Catégorie": "Cuisses / Squats", "Strava_Exercise_Type": "PISTOL_SQUAT", "Exemples FR": "Squat une jambe (Pistol)"},
    {"Catégorie": "Cuisses / Squats", "Strava_Exercise_Type": "WALL_SIT", "Exemples FR": "Chaise contre le mur"},
    {"Catégorie": "Cuisses / Squats", "Strava_Exercise_Type": "JUMP_SQUAT", "Exemples FR": "Squat sauté (pliométrie)"},
    {"Catégorie": "Fentes / Step", "Strava_Exercise_Type": "LUNGE", "Exemples FR": "Fentes avant"},
    {"Catégorie": "Fentes / Step", "Strava_Exercise_Type": "REVERSE_LUNGE", "Exemples FR": "Fentes arrière"},
    {"Catégorie": "Fentes / Step", "Strava_Exercise_Type": "SIDE_LUNGE", "Exemples FR": "Fentes latérales (Cossack)"},
    {"Catégorie": "Fentes / Step", "Strava_Exercise_Type": "WALKING_LUNGE", "Exemples FR": "Fentes marchées"},
    {"Catégorie": "Fentes / Step", "Strava_Exercise_Type": "DUMBBELL_LUNGE", "Exemples FR": "Fentes avec haltères"},
    {"Catégorie": "Fentes / Step", "Strava_Exercise_Type": "STEP_UP", "Exemples FR": "Montée sur banc / boîte (Step-up)"},
    {"Catégorie": "Fentes / Step", "Strava_Exercise_Type": "LATERAL_STEP_UP", "Exemples FR": "Montée latérale / descente excentrique"},
    {"Catégorie": "Mollets / Chevilles / Pieds", "Strava_Exercise_Type": "CALF_RAISE", "Exemples FR": "Extensions mollets deux jambes"},
    {"Catégorie": "Mollets / Chevilles / Pieds", "Strava_Exercise_Type": "SINGLE_LEG_CALF_RAISE", "Exemples FR": "Mollet une jambe (excentrique / Slant board)"},
    {"Catégorie": "Mollets / Chevilles / Pieds", "Strava_Exercise_Type": "SEATED_CALF_RAISE", "Exemples FR": "Mollets assis (soléaire)"},
    {"Catégorie": "Mollets / Chevilles / Pieds", "Strava_Exercise_Type": "WEIGHTED_CALF_RAISE", "Exemples FR": "Mollets lestés avec haltère"},
    {"Catégorie": "Fessiers / Ischios", "Strava_Exercise_Type": "GLUTE_BRIDGE", "Exemples FR": "Pont fessier deux jambes"},
    {"Catégorie": "Fessiers / Ischios", "Strava_Exercise_Type": "SINGLE_LEG_GLUTE_BRIDGE", "Exemples FR": "Pont fessier une jambe"},
    {"Catégorie": "Fessiers / Ischios", "Strava_Exercise_Type": "HIP_THRUST", "Exemples FR": "Hip thrust (relevé de bassin sur banc)"},
    {"Catégorie": "Fessiers / Ischios", "Strava_Exercise_Type": "SINGLE_LEG_DEADLIFT", "Exemples FR": "Soulevé de terre roumain 1 jambe"},
    {"Catégorie": "Fessiers / Ischios", "Strava_Exercise_Type": "ROMANIAN_DEADLIFT", "Exemples FR": "Soulevé de terre jambes tendues"},
    {"Catégorie": "Fessiers / Ischios", "Strava_Exercise_Type": "CLAMSHELL", "Exemples FR": "Palourde (ouverture hanche avec élastique)"},
    {"Catégorie": "Fessiers / Ischios", "Strava_Exercise_Type": "MONSTER_WALK", "Exemples FR": "Marche en crabe / Monster walk (élastique)"},
    {"Catégorie": "Fessiers / Ischios", "Strava_Exercise_Type": "HAMSTRING_CURL", "Exemples FR": "Leg curl / Ischios sur ballon (Swiss ball)"},
    {"Catégorie": "Gainage / Core", "Strava_Exercise_Type": "PLANK_GENERIC", "Exemples FR": "Planche ventrale / Gainage frontal"},
    {"Catégorie": "Gainage / Core", "Strava_Exercise_Type": "SIDE_PLANK", "Exemples FR": "Planche latérale / Gainage costal"},
    {"Catégorie": "Gainage / Core", "Strava_Exercise_Type": "DEAD_BUG", "Exemples FR": "Dead bug"},
    {"Catégorie": "Gainage / Core", "Strava_Exercise_Type": "BIRD_DOG", "Exemples FR": "Bird dog (quadrupédie)"},
    {"Catégorie": "Gainage / Core", "Strava_Exercise_Type": "MOUNTAIN_CLIMBER", "Exemples FR": "Mountain climbers"},
    {"Catégorie": "Gainage / Core", "Strava_Exercise_Type": "SUPERMAN_FROM_FLOOR", "Exemples FR": "Superman / Lombaires au sol"},
    {"Catégorie": "Gainage / Core", "Strava_Exercise_Type": "RUSSIAN_TWIST", "Exemples FR": "Russian twist (obliques)"},
    {"Catégorie": "Gainage / Core", "Strava_Exercise_Type": "HOLLOW_ROCK", "Exemples FR": "Hollow body / Banane"},
    {"Catégorie": "Gainage / Core", "Strava_Exercise_Type": "CRUNCH", "Exemples FR": "Crunch abdominal"},
    {"Catégorie": "Haut du corps", "Strava_Exercise_Type": "PUSH_UP", "Exemples FR": "Pompes"},
    {"Catégorie": "Haut du corps", "Strava_Exercise_Type": "PULL_UP", "Exemples FR": "Tractions"},
    {"Catégorie": "Haut du corps", "Strava_Exercise_Type": "DUMBBELL_ROW", "Exemples FR": "Rowing haltère (dos)"},
    {"Catégorie": "Haut du corps", "Strava_Exercise_Type": "SHOULDER_PRESS", "Exemples FR": "Développé épaules"},
    {"Catégorie": "Haut du corps", "Strava_Exercise_Type": "TRICEP_DIP", "Exemples FR": "Dips triceps"}
]

def obtenir_strava_exercise_type(row):
    """Retourne le Strava_Exercise_Type défini dans le Sheet, ou le déduit automatiquement."""
    val_sheet = str(row.get('Strava_Exercise_Type', '')).strip()
    if val_sheet and val_sheet.lower() not in {"nan", "none", ""}:
        return val_sheet.upper().replace(" ", "_")

    texte = f"{row.get('Nom', '')} {row.get('Zone', '')} {row.get('Description', '')}".lower()
    if "bulgare" in texte or "bulgarian" in texte:
        return "BULGARIAN_SPLIT_SQUAT"
    if "pistol" in texte:
        return "PISTOL_SQUAT"
    if "chaise" in texte or "wall sit" in texte:
        return "WALL_SIT"
    if "goblet" in texte:
        return "GOBLET_SQUAT"
    if "squat" in texte and ("saut" in texte or "jump" in texte):
        return "JUMP_SQUAT"
    if "squat" in texte:
        return "SQUAT"
    if "fente" in texte or "lunge" in texte:
        if "lat" in texte or "cossack" in texte:
            return "SIDE_LUNGE"
        if "arr" in texte or "reverse" in texte:
            return "REVERSE_LUNGE"
        if "march" in texte or "walk" in texte:
            return "WALKING_LUNGE"
        return "LUNGE"
    if "step" in texte or "marche" in texte or "boîte" in texte or "box" in texte:
        if "lat" in texte:
            return "LATERAL_STEP_UP"
        if "mollet" not in texte:
            return "STEP_UP"
    if "mollet" in texte or "achille" in texte or "soléaire" in texte or "soleaire" in texte or "calf" in texte:
        if "assis" in texte or "soléaire" in texte or "soleaire" in texte:
            return "SEATED_CALF_RAISE"
        if "1" in texte or "une jambe" in texte or "unilat" in texte or "excentrique" in texte:
            return "SINGLE_LEG_CALF_RAISE"
        return "CALF_RAISE"
    if "pont" in texte or "bridge" in texte:
        if "1" in texte or "une jambe" in texte or "unilat" in texte:
            return "SINGLE_LEG_GLUTE_BRIDGE"
        return "GLUTE_BRIDGE"
    if "hip thrust" in texte:
        return "HIP_THRUST"
    if "soulevé" in texte or "souleve" in texte or "deadlift" in texte:
        if "1" in texte or "une jambe" in texte or "unilat" in texte:
            return "SINGLE_LEG_DEADLIFT"
        return "ROMANIAN_DEADLIFT"
    if "palourde" in texte or "clamshell" in texte:
        return "CLAMSHELL"
    if "crabe" in texte or "monster" in texte:
        return "MONSTER_WALK"
    if "ischio" in texte and ("ballon" in texte or "swiss" in texte or "curl" in texte):
        return "HAMSTRING_CURL"
    if "planche" in texte or "gainage" in texte or "plank" in texte:
        if "lat" in texte or "costal" in texte or "côté" in texte or "cote" in texte:
            return "SIDE_PLANK"
        return "PLANK_GENERIC"
    if "dead bug" in texte or "deadbug" in texte:
        return "DEAD_BUG"
    if "bird dog" in texte or "birddog" in texte or "quadrup" in texte:
        return "BIRD_DOG"
    if "mountain" in texte:
        return "MOUNTAIN_CLIMBER"
    if "superman" in texte or "lombaire" in texte:
        return "SUPERMAN_FROM_FLOOR"
    if "russian" in texte or "oblique" in texte:
        return "RUSSIAN_TWIST"
    if "hollow" in texte or "banane" in texte:
        return "HOLLOW_ROCK"
    if "pompe" in texte or "push" in texte:
        return "PUSH_UP"
    if "traction" in texte or "pull" in texte:
        return "PULL_UP"
    if "dip" in texte:
        return "TRICEP_DIP"
    if "abdo" in texte or "crunch" in texte:
        return "CRUNCH"

    t_mes = str(row.get('Type_Mesure', 'Temps')).strip().lower()
    return "SQUAT" if t_mes in ['reps', 'répétitions', 'repetitions'] else "PLANK_GENERIC"

def calculer_calories_et_set_exo(row):
    """
    Calcule les calories, le temps actif (sec) et l'objet set Strava d'un exercice
    à partir de sa quantité définie (reps ou secondes) et de Calories_Unitaire
    (kcal/rep si Reps, kcal/minute si Temps).
    """
    try:
        quantite = max(1, int(float(str(row.get('Duree_Defaut', 30)).replace(',', '.'))))
    except Exception:
        quantite = 30

    t_mes = str(row.get('Type_Mesure', 'Temps')).strip().lower()
    is_reps = t_mes in ['reps', 'répétitions', 'repetitions']

    raw_cal = str(row.get('Calories_Unitaire', '')).strip().replace(',', '.')
    val_cal = 0.0
    if raw_cal and raw_cal.lower() not in {'nan', 'none', ''}:
        try:
            val_cal = float(raw_cal)
        except Exception:
            val_cal = 0.0

    ex_type = obtenir_strava_exercise_type(row)

    if is_reps:
        cal_par_rep = val_cal if val_cal > 0 else 0.25  # défaut : 0.25 kcal / répétition
        kcal = quantite * cal_par_rep
        active_sec = quantite * 3  # ~3 sec d'effort actif par répétition
        set_obj = {"exercise_type": ex_type, "repetitions": int(quantite)}
        unite_cal_txt = f"{cal_par_rep:g} kcal/rep"
    else:
        cal_par_min = val_cal if val_cal > 0 else 5.0  # défaut : 5.0 kcal / minute
        kcal = (quantite / 60.0) * cal_par_min
        active_sec = int(quantite)
        set_obj = {"exercise_type": ex_type, "duration": int(quantite)}
        unite_cal_txt = f"{cal_par_min:g} kcal/min"

    return kcal, active_sec, set_obj, unite_cal_txt

def preparer_bilan_strava_seance(df_seance):
    """Retourne (total_kcal, total_active_sec, sets_list, df_recap_sets)."""
    if df_seance is None or df_seance.empty:
        return 0.0, 0, [], pd.DataFrame()

    total_kcal = 0.0
    total_active_sec = 0
    sets_list = []
    lignes_recap = []

    for idx_s, row in df_seance.iterrows():
        kcal, active_sec, set_obj, unite_cal_txt = calculer_calories_et_set_exo(row)
        total_kcal += kcal
        total_active_sec += active_sec
        sets_list.append(set_obj)
        lignes_recap.append({
            "Série #": len(lignes_recap) + 1,
            "Exercice": row.get('Nom', ''),
            "Strava_Exercise_Type": set_obj["exercise_type"],
            "Volume": f"{set_obj['repetitions']} reps" if "repetitions" in set_obj else f"{set_obj['duration']} sec",
            "Base Calcul": unite_cal_txt,
            "Calories (kcal)": round(kcal, 2)
        })

    return round(total_kcal, 1), int(total_active_sec), sets_list, pd.DataFrame(lignes_recap)

def generer_description_strava_renfo(df_seance, nb_tours=1):
    """Génère le texte récapitulatif détaillé d'une séance de renforcement pour Strava."""
    if df_seance is None or df_seance.empty:
        return ""
    total_kcal, total_active_sec, _, _ = preparer_bilan_strava_seance(df_seance)
    zones_s = sorted({
        z.strip()
        for val in df_seance.get('Zone', pd.Series(dtype=str)).dropna().astype(str)
        for z in val.split(',') if z.strip()
    })
    mats_s = extraire_tags_materiel(df_seance['Materiel']) if 'Materiel' in df_seance.columns else []

    lignes = [
        f"💪 Séance de renforcement ({len(df_seance)} séries réalisées | {nb_tours} tour(s))",
        f"🔥 Calories estimées (effort actif) : ~{max(1, int(round(total_kcal)))} kcal ({total_active_sec // 60}m{total_active_sec % 60:02d}s sous tension)"
    ]
    if zones_s:
        lignes.append(f"🎯 Zones ciblées : {', '.join(zones_s)}")
    if mats_s:
        lignes.append(f"🧰 Matériel : {', '.join(mats_s)}")
    else:
        lignes.append("🧰 Matériel : Poids du corps")
    lignes.append("\n📋 Détail des exercices :")

    compteur_exos = {}
    ordre_exos = []
    infos_exos = {}
    kcal_par_exo = {}
    for _, row in df_seance.iterrows():
        nom = str(row.get('Nom_Base') or row.get('Nom', 'Exercice')).strip()
        kcal_e, _, _, _ = calculer_calories_et_set_exo(row)
        if nom not in compteur_exos:
            compteur_exos[nom] = 0
            ordre_exos.append(nom)
            infos_exos[nom] = row
            kcal_par_exo[nom] = 0.0
        compteur_exos[nom] += 1
        kcal_par_exo[nom] += kcal_e

    for nom in ordre_exos:
        r = infos_exos[nom]
        nb_series = compteur_exos[nom]
        is_uni = bool(r.get('Chaque_Jambe', est_unilateral(r.get('Unilateral', ''))))
        uni_txt = " (G+D)" if is_uni else ""
        qte = r.get('Duree_Defaut', '')
        t_mes = str(r.get('Type_Mesure', 'Temps')).strip().lower()
        unite = "reps" if t_mes in ['reps', 'répétitions', 'repetitions'] else "sec"
        mat = str(r.get('Materiel', '')).strip()
        mat_txt = f" [{mat}]" if not est_sans_materiel(mat) else ""
        serie_txt = f"{nb_series} × {qte} {unite}" if nb_series > 1 else f"{qte} {unite}"
        lignes.append(f"• {nom}{uni_txt} : {serie_txt}{mat_txt} (~{kcal_par_exo[nom]:.1f} kcal)")

    lignes.append("\n💬 Ressenti / Notes : ")
    return "\n".join(lignes)

# --- INITIALISATION DE L'IA ---
try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    model = 'gemini-3.8-flash' 
except Exception as e:
    st.error(f"Erreur de configuration de l'IA : {e}")

# ==========================================
# SECTION 1 : SYNCHRONISATION & DONNÉES
# ==========================================
sheets_client.SHEET_ID = st.secrets["SHEET_ID"]
sh = sheets_client.connect_to_sheets()

try:
    ws_renfo = sh.worksheet("Bibliotheque_Renfo")
    df_renfo_loaded = pd.DataFrame(ws_renfo.get_all_records())
    if 'Matériel' in df_renfo_loaded.columns and 'Materiel' not in df_renfo_loaded.columns:
        df_renfo_loaded = df_renfo_loaded.rename(columns={'Matériel': 'Materiel'})
    if not df_renfo_loaded.empty and 'Materiel' not in df_renfo_loaded.columns:
        df_renfo_loaded['Materiel'] = ""
    if not df_renfo_loaded.empty and 'Strava_Exercise_Type' not in df_renfo_loaded.columns:
        df_renfo_loaded['Strava_Exercise_Type'] = ""
    for alias_uni in ('Unilatéral', 'Par_Jambe', 'Chaque_Jambe'):
        if alias_uni in df_renfo_loaded.columns and 'Unilateral' not in df_renfo_loaded.columns:
            df_renfo_loaded = df_renfo_loaded.rename(columns={alias_uni: 'Unilateral'})
    if not df_renfo_loaded.empty and 'Unilateral' not in df_renfo_loaded.columns:
        df_renfo_loaded['Unilateral'] = ""
    if not df_renfo_loaded.empty and 'Calories_Unitaire' not in df_renfo_loaded.columns:
        df_renfo_loaded['Calories_Unitaire'] = ""
    st.session_state['df_renfo'] = df_renfo_loaded
    
    ws_progs = sh.worksheet("Programmes_Renfo")
    st.session_state['df_progs'] = pd.DataFrame(ws_progs.get_all_records())
except Exception:
    st.session_state['df_renfo'] = pd.DataFrame()
    st.session_state['df_progs'] = pd.DataFrame()

strava_client.CLIENT_ID = st.secrets["STRAVA_CLIENT_ID"]
strava_client.CLIENT_SECRET = st.secrets["STRAVA_CLIENT_SECRET"]
strava_client.REFRESH_TOKEN = st.session_state.get("override_strava_refresh_token", st.secrets["STRAVA_REFRESH_TOKEN"])

if 'derniere_analyse' not in st.session_state:
    try:
        ws_analyse = sh.worksheet("Analyses_IA")
        records_analyse = ws_analyse.get_all_records()
        st.session_state['derniere_analyse'] = records_analyse[-1] if records_analyse else None
    except Exception:
        st.session_state['derniere_analyse'] = None

if 'strava_df' not in st.session_state:
    with st.spinner("Synchronisation avec Google Sheets et Strava..."):
        ws_plan = sh.worksheet("5_Plan_4_Semaines")
        df_plan = pd.DataFrame(ws_plan.get_all_records())
        st.session_state['plan_df'] = df_plan
        st.session_state['plan_text'] = df_plan.to_markdown()

        # Lecture de 1_Progression_Annuelle
        try:
            ws_macro = sh.worksheet("1_Progression_Annuelle")
            df_macro = pd.DataFrame(ws_macro.get_all_records())
            st.session_state['macro_text'] = df_macro.to_markdown()
        except Exception:
            st.session_state['macro_text'] = "Progression annuelle non disponible."

        strava_client.CLIENT_ID = st.secrets["STRAVA_CLIENT_ID"]
        strava_client.CLIENT_SECRET = st.secrets["STRAVA_CLIENT_SECRET"]
        strava_client.REFRESH_TOKEN = st.secrets["STRAVA_REFRESH_TOKEN"]
        
        df_strava = strava_client.extract_training_data(sh)
        
        if df_strava is not None and not df_strava.empty:
            st.session_state['strava_df'] = df_strava
        else:
            st.warning("Aucune activité Strava trouvée.")


if 'strava_df' in st.session_state:
    df = st.session_state['strava_df'].reset_index(drop=True)
    df_plan = st.session_state['plan_df']
    macro_text = st.session_state.get('macro_text', '')
    
    tab_activites, tab_plan, tab_renfo = st.tabs(["📊 Activités", "📅 Plan", "💪 Renforcement"])

    # ==========================================
    # ONGLET 1 : ACTIVITÉS
    # ==========================================
    with tab_activites:
        col_titre, col_btn = st.columns([4, 1])
        with col_titre:
            st.subheader("Statistiques globales")
        with col_btn:
            if st.button("🔄 Sync Strava", use_container_width=True):
                del st.session_state['strava_df']
                st.rerun()

        col_dist, col_deniv, col_temps = st.columns(3)
        col_dist.metric("Distance Totale", f"{df['Distance (km)'].sum():.1f} km")
        col_deniv.metric("Dénivelé Total", f"{df['Dénivelé (m)'].sum()} m")
        temps_total = int(df['Temps (min)'].sum())
        col_temps.metric("Temps d'effort", f"{temps_total // 60}h{temps_total % 60:02d}")
        
        st.markdown("---")
        
        # --- GRAPH DOUBLE AXE Y (Centrage, Largeur et ID) ---
        df_graph = df.sort_values('Date', ascending=True)
        dates_uniques = df_graph['Date'].unique()
        labels_courts = [pd.to_datetime(d).strftime('%d/%m') for d in dates_uniques]
        
        fig = go.Figure()
        sports = df_graph['Type'].unique()
        couleurs = px.colors.qualitative.Plotly 
        
        for i, sport in enumerate(sports):
            df_sport = df_graph[df_graph['Type'] == sport]
            is_bike = 'ride' in sport.lower() or 'vélo' in sport.lower()
            
            fig.add_trace(go.Bar(
                x=df_sport['Date'],
                y=df_sport['Distance (km)'],
                name=sport,
                marker_color=couleurs[i % len(couleurs)],
                yaxis='y2' if is_bike else 'y',
                hovertext=df_sport['Nom'],
                customdata=df_sport['ID'], 
                offsetgroup=str(i)
            ))
            
        fig.update_layout(
            title="Volume d'entraînement par sport",
            barmode='group',
            bargap=0.05,       
            bargroupgap=0.0,   
            xaxis=dict(
                type='category',
                categoryorder='array',
                categoryarray=dates_uniques,
                tickmode='array',
                tickvals=dates_uniques,
                ticktext=labels_courts,
                title=""
            ),
            yaxis=dict(title="Km (Course / Foot)"),
            yaxis2=dict(title="Km (Vélo)", overlaying='y', side='right', showgrid=False),
            hovermode='x unified',
            margin=dict(l=0, r=0, t=40, b=0)
        )
        
        selected_idx = 0
        try:
            event = st.plotly_chart(fig, use_container_width=True, on_select="rerun")
            if event and len(event.selection.points) > 0:
                clicked_id = event.selection.points[0].get('customdata')
                if isinstance(clicked_id, list):
                    clicked_id = clicked_id[0]
                matches = df.index[df['ID'].astype(str) == str(clicked_id)].tolist()
                if matches:
                    selected_idx = matches[0]
        except Exception:
            st.plotly_chart(fig, use_container_width=True)

        # --- ANALYSE IA DE LA CHARGE ---
        st.write("") 
        if st.button("🧠 Analyser ma charge d'entraînement (IA)", type="secondary", use_container_width=True):
            with st.spinner("Le coach analyse votre physiologie (et vos notes)..."):
                cols_ia = ['Date', 'Nom', 'Type', 'Distance (km)', 'Dénivelé (m)']
                if 'Notes' in df.columns:
                    cols_ia.append('Notes')
                
                df_recent = df.head(10)[cols_ia]
                details_avances = ""
                for index, row in df.head(5).iterrows():
                    kpi = strava_client.get_advanced_kpis(row['ID'])
                    details_avances += f"- Course du {row['Date']} ({row['Nom']}) : {kpi}\n"
                    
                prompt_analyse = f"""
                Tu es mon coach d'ultra-trail. Je prépare un 65km/4000D+ pour septembre 2027.
                Mes zones cardiaques (FC Max 180) :
                {ZONES_FC_TEXTE}
                Mes 10 dernières activités (inclus mes ressentis/notes) :
                {df_recent.to_markdown()}
                Analyse physiologique des 5 dernières :
                {details_avances}
                Plan actuel :
                {st.session_state['plan_text']}
                Fais une analyse brève (3 points à puces max) de mon état de forme (fatigue, dérive cardiaque, respect du Z2, respect du plan et retours de sensations).
                """
                try:
                    response = client.models.generate_content(model=model, contents=prompt_analyse)
                    date_analyse = datetime.now().strftime("%d/%m/%Y à %H:%M")
                    st.session_state['derniere_analyse'] = {'Date': date_analyse, 'Analyse': response.text}
                    try:
                        try:
                            ws_analyse = sh.worksheet("Analyses_IA")
                        except Exception:
                            ws_analyse = sh.add_worksheet(title="Analyses_IA", rows="200", cols="2")
                            ws_analyse.append_row(["Date", "Analyse"])
                        ws_analyse.append_row([date_analyse, response.text])
                    except Exception as e_sheet:
                        st.warning(f"Analyse non sauvegardée dans le Google Sheet : {e_sheet}")
                    st.success("✅ Nouvelle analyse générée et sauvegardée dans l'onglet 'Analyses_IA' du Google Sheet !")
                except Exception as e:
                    st.error(f"Erreur d'analyse : {e}")

        if st.session_state.get('derniere_analyse'):
            da = st.session_state['derniere_analyse']
            with st.expander(f"🧠 Dernier diagnostic du Coach (sauvegardé le {da.get('Date', '')})", expanded=True):
                st.write(da.get('Analyse', ''))

        # --- DÉTAIL DE L'ACTIVITÉ ---
        st.markdown("---")
        options = df.apply(lambda x: f"{x['Date']} - {x['Nom']} ({x['Distance (km)']} km)", axis=1).tolist()
        choix = st.selectbox("🔎 Détail de l'activité (cliquez sur le graphe ou sélectionnez ici) :", options, index=selected_idx)
        
        if choix:
            idx = options.index(choix)
            act_id = df.iloc[idx]['ID']
            
            note = ""
            if 'Notes' in df.columns:
                val = df.iloc[idx]['Notes']
                if pd.notna(val) and str(val).strip().lower() not in ["", "none", "nan"]:
                    note = str(val).strip()
            
            if not note:
                note = strava_client.get_activity_details(act_id)
                if note:
                    df.at[idx, 'Notes'] = note
                    st.session_state['strava_df'] = df
                    try:
                        ws_hist = sh.worksheet("Historique_Strava")
                        cell = ws_hist.find(str(act_id))
                        if cell:
                            ws_hist.update_cell(cell.row, 10, note)
                    except Exception:
                        pass

            if note:
                st.info(f"📝 **Notes Strava :** {note}")
                    
            if st.toggle("📈 Afficher la télémétrie détaillée (Cardio / Alti / Allure)"):
                with st.spinner("Calcul de la vitesse ajustée et génération du graphique..."):
                    streams = strava_client.get_activity_streams(act_id)
                    
                    if streams and 'distance' in streams and 'time' in streams:
                        df_s = pd.DataFrame({
                            'time': streams['time']['data'],
                            'dist': streams['distance']['data']
                        })
                        
                        df_s['delta_d'] = df_s['dist'].diff().fillna(0)
                        df_s['delta_t'] = df_s['time'].diff().fillna(1)
                        
                        if 'altitude' in streams:
                            df_s['alti'] = streams['altitude']['data']
                            df_s['delta_a'] = df_s['alti'].diff().fillna(0)
                            df_s['delta_d_adj'] = df_s['delta_d'] + df_s['delta_a'].apply(lambda x: x*10 if x > 0 else x*3.3)
                        else:
                            df_s['alti'] = None
                            df_s['delta_d_adj'] = df_s['delta_d']
                            
                        vitesse_brute = (df_s['delta_d'] / df_s['delta_t']).rolling(30, min_periods=1).mean().clip(lower=0.08)
                        df_s['pace'] = (1000 / (vitesse_brute * 60)).clip(2, 20)
                        
                        vitesse_adj = (df_s['delta_d_adj'] / df_s['delta_t']).rolling(30, min_periods=1).mean().clip(lower=0.08)
                        df_s['gap'] = (1000 / (vitesse_adj * 60)).clip(2, 20)
                        
                        if 'heartrate' in streams:
                            df_s['hr'] = streams['heartrate']['data']
                        else:
                            df_s['hr'] = None

                        col_opt, col_graph = st.columns([1, 4])
                        
                        with col_opt:
                            st.write("**Affichage :**")
                            show_hr = st.checkbox("❤️ Cardiaque", value=True) if df_s['hr'].notna().any() else False
                            show_alt = st.checkbox("⛰️ Altitude", value=True) if df_s['alti'].notna().any() else False
                            show_gap = st.checkbox("🏃‍♂️ Allure Ajustée (GAP)", value=False) if df_s['alti'].notna().any() else False
                            show_pace = st.checkbox("⏱️ Allure Brute", value=False)
                            
                        with col_graph:
                            fig_tel = go.Figure()
                            
                            if show_alt:
                                fig_tel.add_trace(go.Scatter(x=df_s['dist']/1000, y=df_s['alti'], fill='tozeroy', mode='none', name='Altitude (m)', fillcolor='rgba(169,169,169,0.3)', yaxis='y2'))
                            if show_pace:
                                fig_tel.add_trace(go.Scatter(x=df_s['dist']/1000, y=df_s['pace'], mode='lines', name='Allure', line=dict(color='#1f77b4', width=1, dash='dot'), yaxis='y3'))
                            if show_gap:
                                fig_tel.add_trace(go.Scatter(x=df_s['dist']/1000, y=df_s['gap'], mode='lines', name='Allure Ajustée', line=dict(color='#2ca02c', width=2), yaxis='y3'))
                            if show_hr:
                                fig_tel.add_trace(go.Scatter(x=df_s['dist']/1000, y=df_s['hr'], mode='lines', name='FC (bpm)', line=dict(color='#d62728', width=2), yaxis='y1'))

                            fig_tel.update_layout(
                                xaxis=dict(title="Distance (km)", domain=[0.1, 1]), 
                                yaxis=dict(title="FC (bpm)", title_font=dict(color="#d62728"), tickfont=dict(color="#d62728")),
                                yaxis2=dict(title="Altitude (m)", overlaying="y", side="right", showgrid=False),
                                yaxis3=dict(title="Allure (min/km)", overlaying="y", side="left", position=0, autorange="reversed", showgrid=False),
                                margin=dict(l=0, r=0, t=30, b=0),
                                hovermode="x unified",
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            st.plotly_chart(fig_tel, use_container_width=True)
                    else:
                        st.warning("Données GPS incomplètes pour analyser cette activité.")

        # --- HISTORIQUE ---
        st.markdown("---")
        st.subheader("Historique Complet")
        st.dataframe(df, use_container_width=True, hide_index=True)


    # ==========================================
    # ONGLET 2 : PLAN D'ENTRAÎNEMENT
    # ==========================================
    with tab_plan:
        st.header("📅 Mon Plan d'Entraînement")
        
        # --- BANDEAU DE RÉFÉRENCE DES 5 ZONES CARDIAQUES (FC MAX 180) ---
        st.markdown("""
        <div style='display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px;'>
            <div style='flex: 1; min-width: 140px; background: #e3f2fd; padding: 8px 12px; border-radius: 6px; border-left: 4px solid #2196f3; font-size: 13px;'>
                <b>Z1 Récupération</b> (50-60%)<br>90 – 108 bpm
            </div>
            <div style='flex: 1; min-width: 140px; background: #e8f5e9; padding: 8px 12px; border-radius: 6px; border-left: 4px solid #4caf50; font-size: 13px;'>
                <b>Z2 Endurance Fond.</b> (60-75%)<br>108 – 135 bpm
            </div>
            <div style='flex: 1; min-width: 140px; background: #fff8e1; padding: 8px 12px; border-radius: 6px; border-left: 4px solid #ffc107; font-size: 13px;'>
                <b>Z3 Tempo / Aérobie</b> (75-85%)<br>135 – 153 bpm
            </div>
            <div style='flex: 1; min-width: 140px; background: #fff3e0; padding: 8px 12px; border-radius: 6px; border-left: 4px solid #ff9800; font-size: 13px;'>
                <b>Z4 Seuil</b> (85-92%)<br>153 – 166 bpm
            </div>
            <div style='flex: 1; min-width: 140px; background: #ffebee; padding: 8px 12px; border-radius: 6px; border-left: 4px solid #f44336; font-size: 13px;'>
                <b>Z5 PMA / Max</b> (92-100%)<br>166 – 180 bpm
            </div>
        </div>
        """, unsafe_allow_html=True)

        jours_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        jour_actuel = jours_fr[datetime.now().weekday()]
        current_week_idx = get_current_week_index(df_plan)

        # 1. Section repliée pour les semaines passées
        if current_week_idx > 0:
            with st.expander(f"📜 Historique des semaines passées ({current_week_idx} semaine(s))", expanded=False):
                for index in range(current_week_idx):
                    row = df_plan.iloc[index]
                    focus_court = str(row.get('Focus', ''))[:65] + ("..." if len(str(row.get('Focus', ''))) > 65 else "")
                    with st.expander(f"{row.get('Semaine', '')} : {row.get('Date', '')} — {focus_court}", expanded=False):
                        render_week_card(row, is_current=False, jour_actuel=jour_actuel, jours_fr=jours_fr)

        # 2. Affichage de la semaine en cours et des semaines futures
        for index in range(current_week_idx, len(df_plan)):
            row = df_plan.iloc[index]
            is_current = (index == current_week_idx)
            focus_court = str(row.get('Focus', ''))[:65] + ("..." if len(str(row.get('Focus', ''))) > 65 else "")
            titre_semaine = (
                f"🟢 SEMAINE EN COURS | {row.get('Semaine', '')} : {row.get('Date', '')} — {focus_court}"
                if is_current else
                f"🔜 {row.get('Semaine', '')} : {row.get('Date', '')} — {focus_court}"
            )
            with st.expander(titre_semaine, expanded=is_current):
                render_week_card(row, is_current=is_current, jour_actuel=jour_actuel, jours_fr=jours_fr)

        st.divider()
        
        # ==========================================
        # SECTION GESTION & GÉNÉRATION DU PLAN
        # ==========================================
        st.header("💬 Pilotage & Évolution du Plan")
        
        mode_action = st.radio(
            "Que souhaitez-vous faire ?",
            ["🛠️ Ajuster une semaine existante", "➕ Générer et ajouter les 4 semaines suivantes"],
            horizontal=True
        )
        
        date_actuelle = datetime.now().strftime("%Y-%m-%d")
        cols_ia = ['Date', 'Nom', 'Type', 'Distance (km)', 'Dénivelé (m)', 'Temps (min)', 'FC Moyenne']
        if 'Notes' in df.columns:
            cols_ia.append('Notes')
        strava_text = df.head(12)[cols_ia].to_markdown()

        df_progs_ia = st.session_state.get('df_progs', pd.DataFrame())
        progs_renfo_text = df_progs_ia.to_markdown(index=False) if not df_progs_ia.empty else "Aucun programme prédéfini."

        df_renfo_ia = st.session_state.get('df_renfo', pd.DataFrame())
        if not df_renfo_ia.empty:
            cols_biblio_ia = [c for c in ['Nom', 'Zone', 'Materiel', 'Type_Mesure', 'Duree_Defaut', 'Description'] if c in df_renfo_ia.columns]
            biblio_renfo_text = df_renfo_ia[cols_biblio_ia].to_markdown(index=False)
        else:
            biblio_renfo_text = "Aucun exercice dans la bibliothèque."

        # ------------------------------------------------------------------
        # ACTION 1 : AJUSTER UNE SEMAINE EXISTANTE
        # ------------------------------------------------------------------
        if mode_action == "🛠️ Ajuster une semaine existante":
            liste_semaines = [f"Ligne {i+2} — {r.get('Semaine', '')} ({r.get('Date', '')})" for i, r in df_plan.iterrows()]
            semaine_choisie = st.selectbox(
                "Sélectionnez la semaine à ajuster :",
                liste_semaines,
                index=min(current_week_idx, max(0, len(liste_semaines)-1))
            )
            ligne_cible_defaut = liste_semaines.index(semaine_choisie) + 2 if liste_semaines else 2
            
            commentaires = st.text_area(
                "Contraintes de la semaine, fatigue ou envies (ex: Retour travail 40km ce vendredi, déplacement jeudi...) :",
                placeholder="Ex: Déplacement pro jeudi, envie de placer le retour à pied 40km/1000D+ vendredi."
            )
            
            prompt_ajustement = f"""Tu es mon coach d'ultra-trail. Objectif : 60km / 4000m D+ en septembre 2027.
Aujourd'hui nous sommes le : {date_actuelle}.

Mes 5 zones de fréquence cardiaque (FC Max = 180 bpm) :
{ZONES_FC_TEXTE}

Règles logistiques et physiologiques impératives :
{REGLES_LOGISTIQUES_COACH}

Fil conducteur annuel (1_Progression_Annuelle) :
{macro_text}

Mes 12 dernières sorties Strava (incluant mes notes privées) :
{strava_text}

Historique et plan actuel complet :
{st.session_state['plan_text']}

Routines de renforcement existantes (onglet Programmes_Renfo) :
{progs_renfo_text}

Catalogue des exercices de renforcement disponibles (onglet Bibliotheque_Renfo) :
{biblio_renfo_text}

Semaine ciblée à modifier : {semaine_choisie} (Ligne {ligne_cible_defaut} dans le Google Sheet).
Contraintes ou demandes du coureur :
{commentaires if commentaires else "Optimise cette semaine selon ma forme actuelle et les règles logistiques."}

Tâche :
1. Ajuste la semaine sélectionnée (ligne {ligne_cible_defaut}) en respectant mes contraintes, la périodisation annuelle et mes règles logistiques (Foot lundi, Vélotaf / Retour à pied 40km 1000D+ le vendredi, Sortie longue le samedi).
2. Dans la colonne 'Focus', rédige le thème suivi d'une explication claire (2 à 3 phrases) de la logique et du but physiologique de la semaine.
3. Indique systématiquement les zones cardiaques (Z1 à Z5 + plage en bpm) dans chaque séance d'endurance.
4. Pour le renforcement musculaire / mobilité : dans la case du jour concerné, nomme CLAIREMENT quelle routine existante de Programmes_Renfo pratiquer (avec le nombre de tours, ex: "Renfo : Routine 'Nom' (3 tours)") OU détaille une séance précise à partir des exercices de Bibliotheque_Renfo. Si pertinent (ou sur demande), définis de nouvelles routines ou de nouveaux exercices adaptés à ma préparation trail.

RÈGLE ABSOLUE : Réponds uniquement en JSON strict avec deux clés :
- "ligne" : {ligne_cible_defaut}
- "donnees" : un tableau de 10 chaînes de caractères correspondant EXACTEMENT aux colonnes [Semaine, Date, Focus, Lundi, Mardi, Mercredi, Jeudi, Vendredi, Samedi, Dimanche].
- "recommandations_renfo" (optionnel, texte) : tes conseils précis sur les séances de renforcement de la semaine et pourquoi tu as choisi ou créé ces routines/exercices.
- "nouveaux_programmes" (optionnel, liste d'objets {{"Nom_Programme": "...", "Exercices": "Nom Exo 1, Nom Exo 2"}}) : si tu me définis une ou plusieurs nouvelles routines.
- "nouveaux_exercices" (optionnel, liste d'objets {{"Nom": "...", "Zone": "...", "Materiel": "...", "Type_Mesure": "Temps ou Reps", "Duree_Defaut": 45, "Description": "...", "Strava_Exercise_Type": "...", "Calories_Unitaire": 5.0}}) : si tu me définis de nouveaux exercices absents de Bibliotheque_Renfo.
Aucun texte avant ou après le JSON."""

            if st.button("🤖 Ajuster la semaine sélectionnée et METTRE À JOUR le Sheet", type="primary", use_container_width=True):
                with st.spinner("Ajustement de la semaine en cours..."):
                    try:
                        for essai in range(3):
                            try:
                                response = client.models.generate_content(model=model, contents=prompt_ajustement)
                                break 
                            except Exception as e:
                                if essai < 2:
                                    time.sleep(4)
                                else:
                                    raise e
                        
                        rep_texte = response.text.replace('```json', '').replace('```', '').strip()
                        brut_json = json.loads(rep_texte)
                        
                        ligne_cible = brut_json.get("ligne", ligne_cible_defaut)
                        if any(brut_json.get(k) for k in ("recommandations_renfo", "nouveaux_programmes", "nouveaux_exercices")):
                            st.session_state['suggestions_renfo_ia'] = {
                                "recommandations_renfo": brut_json.get("recommandations_renfo", ""),
                                "nouveaux_programmes": brut_json.get("nouveaux_programmes", []),
                                "nouveaux_exercices": brut_json.get("nouveaux_exercices", [])
                            }
                        donnees = brut_json.get("donnees", [])
                        while len(donnees) < 10:
                            donnees.append("")
                        donnees = donnees[:10] 
                        
                        ws_plan = sh.worksheet("5_Plan_4_Semaines")
                        ws_plan.update(values=[donnees], range_name=f"A{ligne_cible}:J{ligne_cible}")
                        
                        st.success(f"✅ Semaine mise à jour avec succès sur la ligne {ligne_cible} !")
                        df_plan = pd.DataFrame(ws_plan.get_all_records())               
                        st.session_state['plan_df'] = df_plan                           
                        st.session_state['plan_text'] = df_plan.to_markdown()
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erreur lors de la mise à jour : {e}")

            with st.expander("ℹ️ Voir le prompt de base envoyé à l'IA (Ajustement)", expanded=False):
                st.code(prompt_ajustement, language="text")

        # ------------------------------------------------------------------
        # ACTION 2 : GÉNÉRER ET AJOUTER LES 4 SEMAINES SUIVANTES
        # ------------------------------------------------------------------
        else:
            nb_semaines_actuelles = len(df_plan)
            derniere_semaine_info = df_plan.iloc[-1].to_dict() if not df_plan.empty else {}
            
            consignes_bloc = st.text_area(
                "Indications ou contraintes pour le prochain bloc de 4 semaines (optionnel) :",
                placeholder="Ex: Intégrer un retour du travail à pied (40km/1000D+) un vendredi du bloc, vacances la 3e semaine..."
            )
            
            prompt_generation_4 = f"""Tu es mon coach d'ultra-trail. Objectif : 60km / 4000m D+ en septembre 2027.
Aujourd'hui nous sommes le : {date_actuelle}.

Mes 5 zones de fréquence cardiaque (FC Max = 180 bpm) :
{ZONES_FC_TEXTE}

Règles logistiques et physiologiques impératives :
{REGLES_LOGISTIQUES_COACH}

Fil conducteur annuel (1_Progression_Annuelle) :
{macro_text}

Mes 12 dernières sorties Strava (incluant mes notes privées) :
{strava_text}

Historique complet du plan jusqu'à la dernière semaine planifiée ({derniere_semaine_info.get('Semaine', '')} - {derniere_semaine_info.get('Date', '')}) :
{st.session_state['plan_text']}

Routines de renforcement existantes (onglet Programmes_Renfo) :
{progs_renfo_text}

Catalogue des exercices de renforcement disponibles (onglet Bibliotheque_Renfo) :
{biblio_renfo_text}

Indications particulières du coureur pour ce nouveau bloc de 4 semaines :
{consignes_bloc if consignes_bloc else "Construis une progression logique sur 4 semaines (ex: 3 semaines de charge progressive + 1 semaine d'assimilation) alignée sur 1_Progression_Annuelle."}

Tâche :
1. Génère les 4 semaines qui suivent immédiatement la dernière semaine du plan actuel (numérote-les Semaine {nb_semaines_actuelles + 1} à Semaine {nb_semaines_actuelles + 4}, et calcule exactement les dates du lundi au dimanche au format 'JJ Mmm - JJ Mmm').
2. Pour chaque semaine, rédige dans la colonne 'Focus' le titre du bloc suivi d'une explication claire (2 à 3 phrases) de la logique et du but physiologique des entraînements de la semaine.
3. Indique systématiquement les zones cardiaques (Z1 à Z5 + plage en bpm) pour chaque séance d'endurance, place le football le lundi, privilégie le vendredi pour le vélotaf ou le retour à pied (40km/1000D+), et place les sorties longues le samedi.
4. Pour chaque séance de renforcement / mobilité programmée, nomme CLAIREMENT dans la case du jour quelle routine existante de Programmes_Renfo pratiquer (avec le nombre de tours) OU détaille une séance précise à partir des exercices de Bibliotheque_Renfo. Si pertinent, propose de nouvelles routines ou de nouveaux exercices dans les clés optionnelles du JSON.

RÈGLE ABSOLUE : Réponds uniquement en JSON strict avec une clé "semaines" contenant une liste de 4 listes (chacune ayant exactement 10 éléments : [Semaine, Date, Focus, Lundi, Mardi, Mercredi, Jeudi, Vendredi, Samedi, Dimanche]).
Exemple de structure :
{{"semaines": [["Semaine 5", "16 Nov - 22 Nov", "Développement Aérobie : Logique détaillée...", "Football (Z4/Z5)", "...", "...", "...", "...", "...", "..."], [...], [...], [...]], "recommandations_renfo": "...", "nouveaux_programmes": [{{"Nom_Programme": "...", "Exercices": "Exo 1, Exo 2"}}], "nouveaux_exercices": [{{"Nom": "...", "Zone": "...", "Materiel": "...", "Type_Mesure": "Temps ou Reps", "Duree_Defaut": 45, "Description": "...", "Strava_Exercise_Type": "...", "Calories_Unitaire": 5.0}}]}}
Aucun texte avant ou après le JSON."""

            if st.button("🚀 Générer et AJOUTER les 4 semaines suivantes au Sheet", type="primary", use_container_width=True):
                with st.spinner("Création du nouveau bloc de 4 semaines par le coach IA..."):
                    try:
                        for essai in range(3):
                            try:
                                response = client.models.generate_content(model=model, contents=prompt_generation_4)
                                break 
                            except Exception as e:
                                if essai < 2:
                                    time.sleep(4)
                                else:
                                    raise e
                        
                        rep_texte = response.text.replace('```json', '').replace('```', '').strip()
                        brut_json = json.loads(rep_texte)
                        nouvelles_semaines = brut_json.get("semaines", [])
                        if any(brut_json.get(k) for k in ("recommandations_renfo", "nouveaux_programmes", "nouveaux_exercices")):
                            st.session_state['suggestions_renfo_ia'] = {
                                "recommandations_renfo": brut_json.get("recommandations_renfo", ""),
                                "nouveaux_programmes": brut_json.get("nouveaux_programmes", []),
                                "nouveaux_exercices": brut_json.get("nouveaux_exercices", [])
                            }
                        
                        lignes_propres = []
                        for sem in nouvelles_semaines:
                            while len(sem) < 10:
                                sem.append("")
                            lignes_propres.append(sem[:10])
                            
                        if lignes_propres:
                            ws_plan = sh.worksheet("5_Plan_4_Semaines")
                            ws_plan.append_rows(lignes_propres)
                            
                            st.success(f"✅ {len(lignes_propres)} nouvelles semaines ajoutées avec succès à la suite du plan !")
                            df_plan = pd.DataFrame(ws_plan.get_all_records())               
                            st.session_state['plan_df'] = df_plan                           
                            st.session_state['plan_text'] = df_plan.to_markdown()
                            # Transition directe vers l'écran de publication Strava
                            st.rerun()
                        else:
                            st.error("L'IA n'a renvoyé aucune semaine valide.")
                    except Exception as e:
                        st.error(f"❌ Erreur lors de la génération : {e}")

            with st.expander("ℹ️ Voir le prompt de base envoyé à l'IA (Génération 4 semaines)", expanded=False):
                st.code(prompt_generation_4, language="text")

        if st.session_state.get('suggestions_renfo_ia'):
            sugg = st.session_state['suggestions_renfo_ia']
            with st.expander("💪 Recommandations & Nouvelles séances/exercices proposés par le Coach IA", expanded=True):
                if sugg.get("recommandations_renfo"):
                    st.info(f"🧠 **Conseils Renforcement du Coach :**\n{sugg['recommandations_renfo']}")

                new_exos = sugg.get("nouveaux_exercices") or []
                if new_exos:
                    st.markdown("##### 🆕 Nouveaux exercices proposés (`Bibliotheque_Renfo`) :")
                    df_new_exos = pd.DataFrame(new_exos)
                    st.dataframe(df_new_exos, hide_index=True, use_container_width=True)
                    if st.button("➕ Ajouter ces nouveaux exercices dans 'Bibliotheque_Renfo' (Google Sheet)", key="btn_add_new_exos"):
                        try:
                            ws_r = sh.worksheet("Bibliotheque_Renfo")
                            headers_r = ws_r.row_values(1)
                            rows_to_add = []
                            for ex in new_exos:
                                row_vals = [str(ex.get(col_h, "")) for col_h in headers_r]
                                rows_to_add.append(row_vals)
                            if rows_to_add:
                                ws_r.append_rows(rows_to_add)
                                st.success(f"✅ {len(rows_to_add)} nouvel/nouveaux exercice(s) ajouté(s) à Bibliotheque_Renfo !")
                                sugg["nouveaux_exercices"] = []
                                st.rerun()
                        except Exception as e_add_ex:
                            st.error(f"Erreur lors de l'ajout des exercices : {e_add_ex}")

                new_progs = sugg.get("nouveaux_programmes") or []
                if new_progs:
                    st.markdown("##### 📋 Nouvelles routines proposées (`Programmes_Renfo`) :")
                    df_new_progs = pd.DataFrame(new_progs)
                    st.dataframe(df_new_progs, hide_index=True, use_container_width=True)
                    if st.button("➕ Ajouter ces nouvelles routines dans 'Programmes_Renfo' (Google Sheet)", key="btn_add_new_progs"):
                        try:
                            ws_p = sh.worksheet("Programmes_Renfo")
                            headers_p = ws_p.row_values(1)
                            rows_p_add = []
                            for pr in new_progs:
                                if headers_p:
                                    row_p = [str(pr.get(col_h, "")) for col_h in headers_p]
                                else:
                                    row_p = [str(pr.get("Nom_Programme", "")), str(pr.get("Exercices", ""))]
                                rows_p_add.append(row_p)
                            if rows_p_add:
                                ws_p.append_rows(rows_p_add)
                                st.success(f"✅ {len(rows_p_add)} nouvelle(s) routine(s) ajoutée(s) à Programmes_Renfo !")
                                sugg["nouveaux_programmes"] = []
                                st.rerun()
                        except Exception as e_add_pr:
                            st.error(f"Erreur lors de l'ajout des routines : {e_add_pr}")


    # ==========================================
    # ONGLET 3 : RENFORCEMENT 
    # ==========================================
    with tab_renfo:
        st.header("💪 Séances de Renforcement")

        if st.session_state.get('dernier_bilan_upload_strava'):
            bilan_up = st.session_state['dernier_bilan_upload_strava']
            act_id_up = bilan_up.get('id', '')
            url_act_strava = f"https://www.strava.com/activities/{act_id_up}"
            with st.expander(f"✅ Dernière séance publiée sur Strava (ID : {act_id_up}) — Cliquez pour voir le rapport de vérification", expanded=True):
                st.markdown(
                    f"- 🔗 **Lien direct vers la fiche détaillée de l'activité :** [**Ouvrir sur Strava ({url_act_strava})**]({url_act_strava})  \n"
                    f"  *(Note : sur le « Tableau de bord » Strava, seule la durée s'affiche sur la vignette. Cliquez sur le titre de l'activité ou sur le lien ci-dessus, ou ouvrez l'application mobile Strava, pour voir les calories et les détails)*.\n"
                    f"- 📡 **Méthode d'import retenue par Strava :** `{bilan_up.get('methode', 'Inconnue')}`\n"
                    f"- 🔥 **Calories confirmées par l'API Strava (`GET /activities/{act_id_up}`) :** `{bilan_up.get('calories_strava', 'Non retourné')}` kcal\n"
                    f"- 🏋️ **Type de sport confirmé :** `{bilan_up.get('sport_type_strava', 'WeightTraining')}`"
                )
                if bilan_up.get('note_diag'):
                    st.caption(f"Diagnostic technique Strava : {bilan_up.get('note_diag')}")
                if st.button("✖️ Fermer ce rapport", key="btn_close_bilan_strava"):
                    del st.session_state['dernier_bilan_upload_strava']
                    st.rerun()
        
        if 'df_renfo' in st.session_state and not st.session_state['df_renfo'].empty:
            df_renfo = st.session_state['df_renfo']

            if 'seance_terminee' in st.session_state:
                if st.session_state.pop('afficher_ballons', False):
                    st.balloons()

                st.success("🎉 Bravo ! Votre séance de renforcement est terminée !")
                st.subheader("📤 Publier la séance sur Strava")

                t_start = st.session_state.get('seance_start_time', datetime.now())
                df_seance_finie = st.session_state['seance_terminee']
                kcal_auto, active_sec_auto, sets_strava, df_recap_sets = preparer_bilan_strava_seance(df_seance_finie)

                titre_strava = st.text_input(
                    "🏷️ Titre de l'activité :",
                    value=st.session_state.get('seance_nom_defaut', "💪 Renforcement Trail")
                )
                col_sp, col_dur, col_cal = st.columns(3)
                with col_sp:
                    labels_sports = {
                        "WeightTraining": "🏋️ WeightTraining (Renforcement musculaire)",
                        "Workout": "💪 Workout (Entraînement)",
                        "Crossfit": "🔥 Crossfit",
                        "HighIntensityIntervalTraining": "⚡ HIIT"
                    }
                    sport_strava = st.selectbox(
                        "Type d'activité Strava :",
                        list(labels_sports.keys()),
                        format_func=lambda k: labels_sports[k]
                    )
                with col_dur:
                    duree_defaut_min = max(int(st.session_state.get('strava_duree_min', 15)), max(1, round(active_sec_auto / 60)))
                    duree_strava_min = st.number_input(
                        "⏱️ Durée totale séance (minutes) :",
                        min_value=1,
                        max_value=300,
                        value=duree_defaut_min,
                        help=f"Temps actif sous tension calculé sur les exercices : {active_sec_auto // 60}m{active_sec_auto % 60:02d}s"
                    )
                with col_cal:
                    calories_strava = st.number_input(
                        "🔥 Calories brûlées (kcal, basées sur reps/durée) :",
                        min_value=1,
                        max_value=3000,
                        value=max(1, int(round(kcal_auto))),
                        help="Calculé automatiquement à partir des répétitions / durées définies de chaque exercice réalisé."
                    )

                with st.expander(f"📋 Voir le détail structuré envoyé à Strava ({len(sets_strava)} séries | {active_sec_auto // 60}m{active_sec_auto % 60:02d}s d'effort actif | ~{kcal_auto:.1f} kcal)", expanded=False):
                    st.dataframe(df_recap_sets, hide_index=True, use_container_width=True)

                desc_strava = st.text_area(
                    "📝 Détail de la séance (affiché dans la description Strava) :",
                    value=st.session_state.get('strava_desc_renfo', ''),
                    height=220
                )

                col_pub, col_quit = st.columns([2, 1])
                with col_pub:
                    if st.button("🚀 Envoyer la séance structurée sur Strava (Exercices + Calories)", type="primary", use_container_width=True):
                        with st.spinner("Envoi du fichier d'entraînement structuré (exercices, séries et calories) vers Strava..."):
                            iso_start = t_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                            elapsed_sec = max(int(duree_strava_min) * 60, active_sec_auto)
                            ok, resultat = strava_client.upload_structured_strength_activity(
                                name=titre_strava,
                                sport_type=sport_strava,
                                start_date_local_iso=iso_start,
                                elapsed_time_sec=elapsed_sec,
                                active_time_sec=active_sec_auto,
                                total_calories=calories_strava,
                                sets_list=sets_strava,
                                description=desc_strava
                            )
                            if ok:
                                act_id_new = resultat.get('id', '') if isinstance(resultat, dict) else resultat
                                if isinstance(resultat, dict):
                                    st.session_state['dernier_bilan_upload_strava'] = resultat
                                st.success(f"✅ Séance publiée sur Strava avec succès ! (ID : {act_id_new})")
                                if 'strava_df' in st.session_state:
                                    del st.session_state['strava_df']
                                del st.session_state['seance_terminee']
                                st.rerun()
                            else:
                                st.error(f"❌ Impossible de publier sur Strava : {resultat}")
                                st.session_state['strava_auth_error'] = True
                with col_quit:
                    if st.button("🏠 Quitter sans publier", type="secondary", use_container_width=True):
                        del st.session_state['seance_terminee']
                        st.session_state.pop('strava_auth_error', None)
                        st.rerun()

                with st.expander("🔑 Guide & Assistant : Activer la permission d'écriture Strava (activity:write)", expanded=st.session_state.get('strava_auth_error', False)):
                    client_id_actuel = st.secrets.get("STRAVA_CLIENT_ID", "")
                    auth_url = (
                        f"https://www.strava.com/oauth/authorize?client_id={client_id_actuel}"
                        f"&response_type=code&redirect_uri=http://localhost/exchange_token"
                        f"&approval_prompt=force&scope=read,activity:read_all,activity:write"
                    )
                    st.markdown(
                        "Si vous obtenez une erreur **401 Authorization Error**, c'est que votre `STRAVA_REFRESH_TOKEN` "
                        "actuel n'a que le droit de lecture (`activity:read_all`). Voici comment activer l'écriture en 3 étapes :\n"
                        f"1. **[Cliquez ici pour autoriser l'application sur Strava (avec activity:write)]({auth_url})**.\n"
                        "2. Cochez bien toutes les cases puis cliquez sur **Autoriser**. Vous allez arriver sur une page inaccessible (`localhost/exchange_token?...`) : **c'est normal !**\n"
                        "3. Dans la barre d'adresse de votre navigateur, copiez la valeur située entre `code=` et `&scope=` (ou collez l'URL complète ci-dessous) :"
                    )
                    code_saisi = st.text_input("Collez ici le `code` (ou l'URL complète de redirection `http://localhost/...`) :")
                    if st.button("🔄 Générer mon nouveau STRAVA_REFRESH_TOKEN"):
                        code_propre = code_saisi.strip()
                        if "code=" in code_propre:
                            code_propre = code_propre.split("code=")[1].split("&")[0]
                        if code_propre:
                            ok_tok, res_tok = strava_client.exchange_code_for_tokens(code_propre)
                            if ok_tok:
                                new_rt = res_tok.get("refresh_token", "")
                                st.session_state["override_strava_refresh_token"] = new_rt
                                strava_client.REFRESH_TOKEN = new_rt
                                st.success("✅ Nouveau token actif immédiatement pour cette session ! Vous pouvez cliquer sur '🚀 Envoyer la séance sur Strava' ci-dessus.")
                                st.info("📌 **Pour le sauvegarder définitivement**, remplacez `STRAVA_REFRESH_TOKEN` dans vos Secrets Streamlit (`.streamlit/secrets.toml` ou paramètres Streamlit Cloud) par :")
                                st.code(f'STRAVA_REFRESH_TOKEN = "{new_rt}"', language="toml")
                            else:
                                st.error(f"Erreur lors de l'échange du code : {res_tok}")

            elif 'seance_en_cours' in st.session_state:
                seance = st.session_state['seance_en_cours']
                
                if 'current_exo_index' not in st.session_state:
                    st.session_state['current_exo_index'] = 0
                    
                idx = st.session_state['current_exo_index']
                total_exos = len(seance)
                
                col_btn1, col_btn2 = st.columns([3, 1])
                with col_btn2:
                    if st.button("🛑 Quitter", type="secondary", use_container_width=True):
                        del st.session_state['seance_en_cours']
                        del st.session_state['current_exo_index']
                        st.rerun()
                        
                st.progress((idx + 1) / total_exos)
                exo_actuel = seance.iloc[idx]
                
                col_timeline1, col_timeline2 = st.columns(2)
                with col_timeline1:
                    st.markdown(f"**▶️ En cours ({idx + 1}/{total_exos}) :** {exo_actuel['Nom']}")
                with col_timeline2:
                    if idx + 1 < total_exos:
                        exo_suivant = seance.iloc[idx + 1]
                        st.markdown(f"**⏭️ À suivre :** {exo_suivant['Nom']}")
                    else:
                        st.markdown("**🏁 À suivre : Fin de la séance !**")
                
                st.markdown("---")
                col_media, col_infos = st.columns([1, 1])
                
                with col_media:
                    media_url = str(exo_actuel.get('Media_URL', ''))
                    if media_url:
                        try:
                            if media_url.endswith('.mp4'):
                                st.video(media_url)
                            else:
                                st.image(media_url, use_container_width=True)
                        except Exception:
                            st.warning("Média introuvable.")
                            
                with col_infos:
                    mat_exo = str(exo_actuel.get('Materiel', '')).strip()
                    if not est_sans_materiel(mat_exo):
                        st.markdown(f"🧰 **Matériel :** `{mat_exo}`")
                    st.info(f"**Consignes :**\n{exo_actuel['Description']}")
                    quantite = int(exo_actuel['Duree_Defaut'])
                    type_mesure = str(exo_actuel.get('Type_Mesure', 'Temps')).strip().lower()
                    
                    if type_mesure in ['reps', 'répétitions', 'repetitions']:
                        st.markdown(f"<div style='text-align:center; background-color:#e0f2f1; padding:20px; border-radius:10px;'><h2 style='color:#00796b; margin:0;'>🔄 À faire : {quantite} Répétitions</h2></div>", unsafe_allow_html=True)
                        st.write("")
                        st.info("Prenez le temps nécessaire pour exécuter le mouvement proprement. Cliquez sur 'Suivant' quand vous avez terminé.")
                    else:
                        mode_timer = st.radio("Mode d'exécution :", ["Manuel", "Chronomètre visuel", "Automatique (avec prép.)"], horizontal=True)
                        
                        if mode_timer == "Manuel":
                            st.markdown(f"⏱️ **Durée cible :** {quantite} secondes")
                            
                        elif mode_timer == "Chronomètre visuel":
                            html_code = f"""
                            <div id="chrono_container" style="text-align:center; background-color:#f0f2f6; padding:15px; border-radius:10px;">
                                <h1 id="time" style="font-size:48px; color:#ff4b4b; margin:10px;">{quantite}</h1>
                                <button onclick="startTimer()" style="padding:10px 20px; border-radius:5px; border:none; background-color:#ff4b4b; color:white; font-weight:bold;">Play / Pause</button>
                            </div>
                            <script>
                                var timeLeft = {quantite};
                                var timerId = null;
                                var isRunning = false;
                                function startTimer() {{
                                    if(isRunning) {{ clearInterval(timerId); isRunning = false; }} 
                                    else {{
                                        isRunning = true;
                                        timerId = setInterval(function() {{
                                            if(timeLeft <= 0) {{ clearInterval(timerId); document.getElementById('time').innerHTML = "TERMINÉ !"; document.getElementById('time').style.color = "#4CAF50"; }} 
                                            else {{ document.getElementById('time').innerHTML = timeLeft; timeLeft -= 1; }}
                                        }}, 1000);
                                    }}
                                }}
                            </script>
                            """
                            components.html(html_code, height=160)
                            
                        elif mode_timer == "Automatique (avec prép.)":
                            prep_time = st.number_input("⏱️ Préparation (sec) :", min_value=1, max_value=60, value=10)
                            html_code = f"""
                            <div id="chrono_container" style="text-align:center; background-color:#f0f2f6; padding:15px; border-radius:10px;">
                                <h3 id="status" style="margin:0; color:#ff9800;">PRÉPARATION</h3>
                                <h1 id="time" style="font-size:48px; color:#ff9800; margin:5px;">{prep_time}</h1>
                                <button onclick="toggleTimer()" style="padding:5px 15px; border-radius:5px; border:none; background-color:#333; color:white;">Pause / Reprendre</button>
                            </div>
                            <script>
                                var phase = "prep"; var timeLeft = {prep_time}; var workTime = {quantite};
                                var timerId = null; var isRunning = true;
                                function updateDisplay() {{
                                    if (timeLeft <= 0) {{
                                        if (phase === "prep") {{ phase = "work"; timeLeft = workTime; document.getElementById('status').innerHTML = "🔥 GO GO GO !"; document.getElementById('status').style.color = "#ff4b4b"; document.getElementById('time').style.color = "#ff4b4b"; }} 
                                        else {{
                                            clearInterval(timerId); document.getElementById('status').innerHTML = "✅ TERMINÉ"; document.getElementById('status').style.color = "#4CAF50"; document.getElementById('time').innerHTML = "0"; document.getElementById('time').style.color = "#4CAF50";
                                            setTimeout(function() {{
                                                var parentDoc = window.parent.document;
                                                var nextBtn = parentDoc.evaluate("//button[contains(., 'Suivant ➡️')]", parentDoc, null, window.parent.XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                                if (nextBtn) {{ nextBtn.click(); }} else {{
                                                    var finishBtn = parentDoc.evaluate("//button[contains(., '🎉 Terminer')]", parentDoc, null, window.parent.XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                                    if (finishBtn) {{ finishBtn.click(); }}
                                                }}
                                            }}, 2000); return;
                                        }}
                                    }}
                                    document.getElementById('time').innerHTML = timeLeft; timeLeft -= 1;
                                }}
                                function toggleTimer() {{ if(isRunning) {{ clearInterval(timerId); isRunning = false; }} else {{ isRunning = true; timerId = setInterval(updateDisplay, 1000); }} }}
                                document.getElementById('time').innerHTML = timeLeft; timeLeft -= 1; timerId = setInterval(updateDisplay, 1000);
                            </script>
                            """
                            components.html(html_code, height=180)
                            
                st.write("")
                col_prev, col_next = st.columns(2)
                with col_prev:
                    if idx > 0:
                        if st.button("⬅️ Précédent", use_container_width=True):
                            st.session_state['current_exo_index'] -= 1
                            st.rerun()
                with col_next:
                    if idx < total_exos - 1:
                        if st.button("Suivant ➡️", use_container_width=True):
                            st.session_state['current_exo_index'] += 1
                            st.rerun()
                    else:
                        if st.button("🎉 Terminer la séance", type="primary", use_container_width=True):
                            t_start = st.session_state.get('seance_start_time', datetime.now())
                            duree_reelle = max(1, round((datetime.now() - t_start).total_seconds() / 60))
                            st.session_state['seance_terminee'] = seance
                            st.session_state['strava_duree_min'] = duree_reelle
                            st.session_state['strava_desc_renfo'] = generer_description_strava_renfo(
                                seance,
                                st.session_state.get('seance_nb_tours', 1)
                            )
                            st.session_state['afficher_ballons'] = True
                            del st.session_state['seance_en_cours']
                            del st.session_state['current_exo_index']
                            # Transition directe vers l'écran de publication Strava
                            st.rerun()

            else:
                def reset_brouillon():
                    st.session_state['editeur_version'] = st.session_state.get('editeur_version', 0) + 1
                    if 'seance_brouillon' in st.session_state:
                        del st.session_state['seance_brouillon']

                def reset_tours():
                    st.session_state['editeur_version'] = st.session_state.get('editeur_version', 0) + 1
                    if 'seance_brouillon' in st.session_state:
                        del st.session_state['seance_brouillon']

                toutes_zones = df_renfo['Zone'].astype(str).str.split(',').explode().str.strip()
                zones_dispos = sorted([z for z in toutes_zones.unique() if z != ""])
                materiels_dispos = extraire_tags_materiel(df_renfo['Materiel']) if 'Materiel' in df_renfo.columns else []

                col_mode, col_tours = st.columns([2, 1])
                with col_mode:
                    mode = st.radio(
                        "Mode de création :", 
                        ["Programme Prédéfini", "Aléatoire Total", "Aléatoire par Zone", "Sélection Manuelle", "Constructeur par Zone"], 
                        horizontal=True,
                        on_change=reset_brouillon
                    )
                with col_tours:
                    nb_tours = st.number_input("🔄 Nombre de tours (circuits) :", min_value=1, max_value=10, value=1, on_change=reset_tours)
                    
                st.markdown("---")
                
                if mode == "Aléatoire Total":
                    max_total = len(df_renfo)
                    nb_exos = st.slider("Exercices par tour :", 1, max_total, min(5, max_total)) if max_total > 1 else 1
                    if max_total > 0 and st.button("Générer la séance"):
                        base = df_renfo.sample(n=nb_exos)
                        st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                        
                elif mode == "Aléatoire par Zone":
                    zone_choisie = st.selectbox("Zone ciblée (Tag) :", zones_dispos)
                    exos_possibles = df_renfo[df_renfo['Zone'].astype(str).str.contains(zone_choisie, case=False, na=False, regex=False)]
                    max_exos = len(exos_possibles)
                    nb_exos = st.slider(f"Exercices contenant '{zone_choisie}' par tour :", 1, max_exos, min(3, max_exos)) if max_exos > 1 else 1
                    if max_exos > 0 and st.button("Générer la séance"):
                        base = exos_possibles.sample(n=nb_exos)
                        st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                        
                elif mode == "Sélection Manuelle":
                    col_f_z, col_f_m = st.columns(2)
                    with col_f_z:
                        zones_sel = st.multiselect("🎯 Filtrer par Zone :", zones_dispos, placeholder="Toutes les zones")
                    with col_f_m:
                        options_mat_filtre = ["Sans matériel (Poids du corps)"] + materiels_dispos
                        mat_sel = st.multiselect("🧰 Filtrer par Matériel :", options_mat_filtre, placeholder="Tout le matériel")

                    df_manuel_filtre = df_renfo.copy()
                    if zones_sel:
                        mask_z = df_manuel_filtre['Zone'].astype(str).apply(
                            lambda val: any(z.lower() in [p.strip().lower() for p in val.split(',')] for z in zones_sel)
                        )
                        df_manuel_filtre = df_manuel_filtre[mask_z]
                    if mat_sel:
                        inclure_sans = "Sans matériel (Poids du corps)" in mat_sel
                        tags_mat_cibles = [m.lower() for m in mat_sel if m != "Sans matériel (Poids du corps)"]
                        def match_materiel(val):
                            if est_sans_materiel(val):
                                return inclure_sans
                            parts = [p.strip().lower() for p in str(val).split(',')]
                            return any(t in parts for t in tags_mat_cibles)
                        df_manuel_filtre = df_manuel_filtre[df_manuel_filtre['Materiel'].apply(match_materiel)]

                    deja_choisis = st.session_state.get("multiselect_exos_manuels", [])
                    noms_filtres = df_manuel_filtre['Nom'].tolist()
                    options_multiselect = list(dict.fromkeys([n for n in deja_choisis if n in df_renfo['Nom'].values] + noms_filtres))

                    st.caption(f"🔎 {len(noms_filtres)} exercice(s) correspondant aux filtres actifs.")
                    exos_choisis = st.multiselect(
                        "Choisissez vos exercices pour 1 tour :",
                        options_multiselect,
                        key="multiselect_exos_manuels"
                    )
                    if st.button("Valider la séance") and exos_choisis:
                        base = df_renfo[df_renfo['Nom'].isin(exos_choisis)]
                        st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                        
                elif mode == "Constructeur par Zone":
                    choix_zones = {}
                    cols = st.columns(4) 
                    for i, zone in enumerate(zones_dispos):
                        exos_in_zone = df_renfo[df_renfo['Zone'].astype(str).str.contains(zone, case=False, na=False, regex=False)]
                        max_exos = len(exos_in_zone)
                        with cols[i % 4]:
                            choix = st.number_input(f"{zone} (Max: {max_exos})", 0, max_exos, 0, key=f"zone_{zone}")
                            choix_zones[zone] = choix
                    
                    if st.button("Assembler la séance combinée"):
                        frames = []
                        for zone, nb in choix_zones.items():
                            if nb > 0:
                                exos_in_zone = df_renfo[df_renfo['Zone'].astype(str).str.contains(zone, case=False, na=False, regex=False)]
                                frames.append(exos_in_zone.sample(n=nb))
                        if frames:
                            base = pd.concat(frames).drop_duplicates(subset=['Nom'])
                            st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                
                elif mode == "Programme Prédéfini":
                    if 'df_progs' in st.session_state and not st.session_state['df_progs'].empty:
                        liste_progs = st.session_state['df_progs']['Nom_Programme'].tolist()
                        prog_choisi = st.selectbox("Choisissez votre routine :", liste_progs, on_change=reset_brouillon)
                        
                        if st.button("Charger la routine prédéfinie"):
                            exos_str = st.session_state['df_progs'].loc[st.session_state['df_progs']['Nom_Programme'] == prog_choisi, 'Exercices'].values[0]
                            liste_noms = [nom.strip() for nom in str(exos_str).split(',')]
                            exos_list = []
                            for nom in liste_noms:
                                match = df_renfo[df_renfo['Nom'].str.lower() == nom.lower()]
                                if not match.empty:
                                    exos_list.append(match.iloc[0])
                            if exos_list:
                                base = pd.DataFrame(exos_list).reset_index(drop=True)
                                st.session_state['editeur_version'] = st.session_state.get('editeur_version', 0) + 1
                                st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                
                if 'seance_brouillon' in st.session_state and not st.session_state['seance_brouillon'].empty:
                    df_brouillon = st.session_state['seance_brouillon'].copy()
                    if 'Actif' not in df_brouillon.columns:
                        df_brouillon.insert(0, 'Actif', True)
                    if 'Chaque_Jambe' not in df_brouillon.columns:
                        val_uni_init = df_brouillon['Unilateral'].apply(est_unilateral) if 'Unilateral' in df_brouillon.columns else False
                        df_brouillon.insert(1, 'Chaque_Jambe', val_uni_init)
                    conteneur_resume = st.container()
                    cols_infos = [c for c in ['Nom', 'Zone', 'Materiel', 'Duree_Defaut', 'Description'] if c in df_brouillon.columns]
                    df_edite = st.data_editor(
                        df_brouillon[['Actif', 'Chaque_Jambe'] + cols_infos],
                        column_config={
                            "Actif": st.column_config.CheckboxColumn(
                                "✅ Actif",
                                help="Décochez pour désactiver cet exercice de la séance",
                                default=True
                            ),
                            "Chaque_Jambe": st.column_config.CheckboxColumn(
                                "🦵 Chaque jambe (G+D)",
                                help="Si coché, l'exercice sera doublé (Jambe/Côté Gauche puis Jambe/Côté Droit) pendant la séance",
                                default=False
                            )
                        },
                        disabled=cols_infos,
                        hide_index=True,
                        use_container_width=True,
                        key=f"editeur_seance_{st.session_state.get('editeur_version', 0)}"
                    )
                    st.session_state['seance_brouillon']['Actif'] = df_edite['Actif'].values
                    st.session_state['seance_brouillon']['Chaque_Jambe'] = df_edite['Chaque_Jambe'].values
                    seance_active_brute = st.session_state['seance_brouillon'][st.session_state['seance_brouillon']['Actif'] == True].drop(columns=['Actif']).reset_index(drop=True)
                    seance_prete = deplier_exercices_unilateraux(seance_active_brute)

                    with conteneur_resume:
                        if not seance_prete.empty:
                            nb_uni = int(seance_active_brute['Chaque_Jambe'].sum()) if 'Chaque_Jambe' in seance_active_brute.columns else 0
                            precision_uni = f" dont {nb_uni} en G+D → **{len(seance_prete)} séquences au total**" if nb_uni > 0 else ""
                            st.success(f"✅ Séance prête : {len(seance_active_brute)} exercice(s) actif(s){precision_uni}. Cochez '🦵 Chaque jambe (G+D)' pour doubler un exercice (Gauche puis Droite).")
                            materiels_seance = extraire_tags_materiel(seance_prete['Materiel']) if 'Materiel' in seance_prete.columns else []
                            if materiels_seance:
                                st.warning(f"🧰 **Matériel nécessaire pour cette séance :** {', '.join(materiels_seance)}")
                            else:
                                st.info("🧰 **Matériel nécessaire pour cette séance :** Aucun (Poids du corps uniquement)")
                        else:
                            st.warning("⚠️ Aucun exercice actif sélectionné. Cochez au moins un exercice dans le tableau pour lancer la séance.")
                    if st.button("▶️ DÉMARRER L'ENTRAÎNEMENT", type="primary", use_container_width=True, disabled=seance_prete.empty):
                        st.session_state['seance_en_cours'] = seance_prete
                        st.session_state['seance_start_time'] = datetime.now()
                        st.session_state['seance_nb_tours'] = nb_tours
                        st.session_state['seance_nom_defaut'] = (
                            f"💪 Renforcement Trail - {prog_choisi}"
                            if mode == "Programme Prédéfini" and 'prog_choisi' in locals()
                            else f"💪 Renforcement Trail ({mode})"
                        )
                        if 'routine_base' in st.session_state:
                            del st.session_state['routine_base']
                        st.session_state['current_exo_index'] = 0
                        del st.session_state['seance_brouillon']
                        st.rerun()
        else:
            st.info("Pour activer ce module, créez l'onglet 'Bibliotheque_Renfo'.")

        # --- ESPACE BIBLIOTHÈQUE (Masqué par défaut et masqué pendant une séance) ---
        if 'df_renfo' in st.session_state and not st.session_state['df_renfo'].empty and 'seance_en_cours' not in st.session_state and 'seance_terminee' not in st.session_state:
            df_renfo_biblio = st.session_state['df_renfo'].copy()
            st.markdown("---")
            with st.expander(f"📚 Bibliothèque complète des exercices ({len(df_renfo_biblio)} exercices)", expanded=False):
                if 'Media_URL' in df_renfo_biblio.columns:
                    df_renfo_biblio['Statut Média'] = df_renfo_biblio['Media_URL'].apply(verifier_disponibilite_media)
                else:
                    df_renfo_biblio['Statut Média'] = "❌ Non renseigné"

                nb_total_exos = len(df_renfo_biblio)
                nb_media_ok = int((df_renfo_biblio['Statut Média'] == "✅ Disponible").sum())
                nb_media_ko = nb_total_exos - nb_media_ok

                col_m1, col_m2, col_m3, col_m4 = st.columns([1, 1, 1, 1])
                col_m1.metric("Total exercices", nb_total_exos)
                col_m2.metric("Médias disponibles", f"{nb_media_ok} ✅")
                col_m3.metric("Médias manquants", f"{nb_media_ko} ❌")
                with col_m4:
                    st.write("")
                    if st.button("🔄 Actualiser la vérification", use_container_width=True):
                        verifier_disponibilite_media.clear()
                        st.rerun()

                col_f_zone, col_f_mat, col_f_statut = st.columns(3)
                with col_f_zone:
                    toutes_zones_biblio = df_renfo_biblio['Zone'].astype(str).str.split(',').explode().str.strip() if 'Zone' in df_renfo_biblio.columns else pd.Series(dtype=str)
                    zones_biblio = sorted([z for z in toutes_zones_biblio.unique() if z != ""])
                    filtre_zone = st.selectbox("Filtrer par zone :", ["Toutes les zones"] + zones_biblio, key="biblio_filtre_zone")
                with col_f_mat:
                    mats_biblio = extraire_tags_materiel(df_renfo_biblio['Materiel']) if 'Materiel' in df_renfo_biblio.columns else []
                    filtre_mat = st.selectbox("Filtrer par matériel :", ["Tout", "Sans matériel"] + mats_biblio, key="biblio_filtre_mat")
                with col_f_statut:
                    filtre_statut = st.selectbox(
                        "Filtrer par statut média :",
                        ["Tous", "✅ Disponible uniquement", "❌ Manquant / Introuvable uniquement"],
                        key="biblio_filtre_statut"
                    )

                df_affiche = df_renfo_biblio.copy()
                if filtre_zone != "Toutes les zones" and 'Zone' in df_affiche.columns:
                    df_affiche = df_affiche[df_affiche['Zone'].astype(str).str.contains(filtre_zone, case=False, na=False, regex=False)]
                if filtre_mat != "Tout" and 'Materiel' in df_affiche.columns:
                    if filtre_mat == "Sans matériel":
                        df_affiche = df_affiche[df_affiche['Materiel'].apply(est_sans_materiel)]
                    else:
                        df_affiche = df_affiche[df_affiche['Materiel'].astype(str).str.contains(filtre_mat, case=False, na=False, regex=False)]
                if filtre_statut == "✅ Disponible uniquement":
                    df_affiche = df_affiche[df_affiche['Statut Média'] == "✅ Disponible"]
                elif filtre_statut == "❌ Manquant / Introuvable uniquement":
                    df_affiche = df_affiche[df_affiche['Statut Média'] != "✅ Disponible"]

                df_affiche['Strava_Type_Effectif'] = df_affiche.apply(
                    lambda r: str(r.get('Strava_Exercise_Type', '')).strip() or f"{obtenir_strava_exercise_type(r)} (auto)",
                    axis=1
                )
                colonnes_ordre = ['Nom', 'Zone', 'Materiel', 'Unilateral', 'Statut Média', 'Type_Mesure', 'Duree_Defaut', 'Calories_Unitaire', 'Strava_Type_Effectif', 'Description', 'Media_URL']
                colonnes_finales = [c for c in colonnes_ordre if c in df_affiche.columns] + [c for c in df_affiche.columns if c not in colonnes_ordre and c != 'Strava_Exercise_Type']

                st.dataframe(df_affiche[colonnes_finales], use_container_width=True, hide_index=True)

                with st.expander("📖 Référence : Codes d'exercices Strava (`Strava_Exercise_Type`) & `Calories_Unitaire` pour le Google Sheet", expanded=False):
                    st.markdown(
                        "- **`Strava_Exercise_Type`** : copiez l'un des codes officiels ci-dessous dans votre Google Sheet (si laissé vide, l'application choisit automatiquement le code marqué `(auto)` dans le tableau ci-dessus).\n"
                        "- **`Calories_Unitaire`** : indiquez les **kcal par répétition** si `Type_Mesure = Reps` (défaut auto : `0.25` kcal/rep) ou les **kcal par minute** si `Type_Mesure = Temps` (défaut auto : `5.0` kcal/min)."
                    )
                    st.dataframe(pd.DataFrame(CATALOGUE_STRAVA_EXERCICES), use_container_width=True, hide_index=True)

                exo_apercu = st.selectbox(
                    "👁️ Tester / Prévisualiser le média d'un exercice :",
                    ["— Aucun —"] + df_affiche['Nom'].tolist() if 'Nom' in df_affiche.columns else ["— Aucun —"],
                    key="biblio_apercu_exo"
                )
                if exo_apercu != "— Aucun —":
                    ligne_exo = df_affiche[df_affiche['Nom'] == exo_apercu].iloc[0]
                    col_prev_media, col_prev_desc = st.columns([1, 1])
                    with col_prev_media:
                        url_test = str(ligne_exo.get('Media_URL', '')).strip()
                        if ligne_exo.get('Statut Média') == "✅ Disponible" and url_test:
                            try:
                                if url_test.lower().endswith('.mp4'):
                                    st.video(url_test)
                                else:
                                    st.image(url_test, use_container_width=True)
                            except Exception:
                                st.warning("Impossible de charger l'aperçu du média.")
                        else:
                            st.warning(f"Média indisponible ({ligne_exo.get('Statut Média', 'Inconnu')}) — Chemin/URL : `{url_test or 'Vide'}`")
                    with col_prev_desc:
                        st.markdown(f"**{ligne_exo.get('Nom', '')}** ({ligne_exo.get('Zone', '')})")
                        st.info(f"**Consignes :**\n{ligne_exo.get('Description', '')}")
                        st.caption(f"Mesure : {ligne_exo.get('Duree_Defaut', '')} ({ligne_exo.get('Type_Mesure', 'Temps')}) | Média : `{url_test or 'Non renseigné'}`")