import requests
import pandas as pd
from datetime import datetime
import time
import gspread

CLIENT_ID = ""
CLIENT_SECRET = ""
REFRESH_TOKEN = ""

HIGH_INTENSITY_KEYWORDS = (
    "foot", "soccer", "football", "fractionn", "vma", "pma", "seuil",
    "interval", "hiit", "sprint", "compétition", "competition", "race",
    "tempo", "côte", "cote", "test", "intens"
)


def _round_bpm(val):
    return int(float(val) + 0.5)


def _resolve_fc_zones(fc_config=None):
    """Retourne (fc_max_ref, z2_min, z3_min, z4_min, z5_min) à partir de fc_config."""
    if isinstance(fc_config, dict) and fc_config.get("zones"):
        fc_max_ref = float(fc_config.get("fc_max_raw", fc_config.get("fc_max", 187)))
        zones = fc_config["zones"]
        z2_min = float(zones.get("Z2", {}).get("min_bpm", zones.get("Z1", {}).get("max_bpm", fc_max_ref * 0.60)))
        z3_min = float(zones.get("Z3", {}).get("min_bpm", zones.get("Z2", {}).get("max_bpm", fc_max_ref * 0.75)))
        z4_min = float(zones.get("Z4", {}).get("min_bpm", zones.get("Z3", {}).get("max_bpm", fc_max_ref * 0.85)))
        z5_min = float(zones.get("Z5", {}).get("min_bpm", zones.get("Z4", {}).get("max_bpm", fc_max_ref * 0.92)))
        return fc_max_ref, z2_min, z3_min, z4_min, z5_min

    fc_max_ref = 187.0
    return (
        fc_max_ref,
        round(fc_max_ref * 0.60, 2),
        round(fc_max_ref * 0.75, 2),
        round(fc_max_ref * 0.85, 2),
        round(fc_max_ref * 0.92, 2),
    )


def _matches_high_intensity_label(activity_name="", activity_type=""):
    texte = f"{activity_name or ''} {activity_type or ''}".lower()
    return any(kw in texte for kw in HIGH_INTENSITY_KEYWORDS)


def is_high_intensity_session(
    activity_name="",
    activity_type="",
    hr_max_seance=None,
    hr_avg=None,
    z4_pct=None,
    z5_pct=None,
    fc_config=None,
):
    """Détermine si une séance correspond à une séance à haute intensité."""
    _, _, z3_min, z4_min, z5_min = _resolve_fc_zones(fc_config)
    kw_match = _matches_high_intensity_label(activity_name, activity_type)

    if z4_pct is not None and z5_pct is not None:
        if (z4_pct + z5_pct) >= 15.0 or z5_pct >= 3.0:
            return True
        if hr_max_seance is not None and hr_max_seance >= z5_min:
            return True
        if kw_match and (hr_max_seance is None or hr_max_seance >= z4_min):
            return True
        return False

    if hr_max_seance is not None and hr_max_seance >= z5_min:
        return True
    if hr_avg is not None and hr_avg >= z4_min:
        return True
    if kw_match:
        if hr_max_seance is not None and hr_max_seance >= z4_min:
            return True
        if hr_avg is not None and hr_avg >= z3_min:
            return True
    return False


def format_fc_max_comparison(hr_max_seance, fc_max_ref):
    """
    Compare sommairement la FC max atteinte sur une séance à la FC max de référence.
    Retourne (texte_comparaison, est_au_dessus_ref).
    """
    hr_int = _round_bpm(hr_max_seance)
    ref_int = _round_bpm(fc_max_ref)
    diff = hr_int - ref_int
    pct = (float(hr_max_seance) / float(fc_max_ref) * 100.0) if fc_max_ref > 0 else 0.0

    if diff > 0:
        return (
            f"{hr_int} bpm (+{diff} bpm vs FC max actuelle {ref_int} bpm, soit {pct:.0f}% — au-dessus de la référence, mise à jour à envisager dans FC_max si la mesure est fiable)",
            True,
        )
    if diff == 0:
        return (
            f"{hr_int} bpm (égale à la FC max actuelle de {ref_int} bpm, 100%)",
            False,
        )
    if diff >= -5:
        return (
            f"{hr_int} bpm ({diff} bpm vs FC max actuelle {ref_int} bpm, soit {pct:.0f}% — très proche de la référence)",
            False,
        )
    return (
        f"{hr_int} bpm ({diff} bpm vs FC max actuelle {ref_int} bpm, soit {pct:.0f}% — en dessous de la référence)",
        False,
    )


def compute_hr_stats_from_data(hr_data, fc_config=None, activity_name="", activity_type=""):
    """Calcule la répartition Z1-Z5, la dérive FC, la FC max atteinte et le statut haute intensité."""
    clean_hr = [float(h) for h in hr_data if h is not None and h > 0]
    if len(clean_hr) < 10:
        return None

    fc_max_ref, z2_min, z3_min, z4_min, z5_min = _resolve_fc_zones(fc_config)
    n = len(clean_hr)
    z1 = sum(1 for h in clean_hr if h < z2_min) / n * 100
    z2 = sum(1 for h in clean_hr if z2_min <= h < z3_min) / n * 100
    z3 = sum(1 for h in clean_hr if z3_min <= h < z4_min) / n * 100
    z4 = sum(1 for h in clean_hr if z4_min <= h < z5_min) / n * 100
    z5 = sum(1 for h in clean_hr if h >= z5_min) / n * 100

    mid = n // 2
    hr_first = sum(clean_hr[:mid]) / mid if mid > 0 else 0.0
    hr_second = sum(clean_hr[mid:]) / (n - mid) if (n - mid) > 0 else 0.0
    derive = hr_second - hr_first

    hr_max = max(clean_hr)
    hr_avg = sum(clean_hr) / n
    high_int = is_high_intensity_session(
        activity_name=activity_name,
        activity_type=activity_type,
        hr_max_seance=hr_max,
        hr_avg=hr_avg,
        z4_pct=z4,
        z5_pct=z5,
        fc_config=fc_config,
    )
    comp_txt, above_ref = format_fc_max_comparison(hr_max, fc_max_ref)

    return {
        "fc_max_ref": _round_bpm(fc_max_ref),
        "hr_max": _round_bpm(hr_max),
        "hr_avg": _round_bpm(hr_avg),
        "z1": z1,
        "z2": z2,
        "z3": z3,
        "z4": z4,
        "z5": z5,
        "derive": derive,
        "is_high_intensity": high_int,
        "comparison_text": comp_txt,
        "is_above_ref": above_ref,
        "boundaries": (
            _round_bpm(z2_min),
            _round_bpm(z3_min),
            _round_bpm(z4_min),
            _round_bpm(z5_min),
        ),
    }


def get_access_token():
    url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': REFRESH_TOKEN,
        'grant_type': 'refresh_token',
        'f': 'json'
    }
    response = requests.post(url, data=payload)
    response.raise_for_status()
    return response.json().get('access_token')


def extract_training_data(sh):
    try:
        ws = sh.worksheet("Historique_Strava")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="Historique_Strava", rows="1000", cols="20")
        en_tetes = ['ID', 'Date', 'Date_API', 'Type', 'Nom', 'Distance (km)', 'Dénivelé (m)', 'Temps (min)', 'FC Moyenne', 'Notes', 'FC Max']
        ws.append_row(en_tetes)

    sheet_headers = ws.row_values(1)
    if sheet_headers and 'FC Max' not in sheet_headers:
        try:
            next_col = len(sheet_headers) + 1
            if ws.col_count < next_col:
                ws.add_cols(1)
            ws.update_cell(1, next_col, 'FC Max')
            sheet_headers.append('FC Max')
        except Exception:
            pass

    donnees = ws.get_all_records()
    df_hist = pd.DataFrame(donnees)

    ids_existants = set()

    if not df_hist.empty:
        last_date_str = df_hist['Date_API'].max()
        dt_obj = datetime.strptime(last_date_str, "%Y-%m-%dT%H:%M:%SZ")
        after_timestamp = int(dt_obj.timestamp())
        ids_existants = set(df_hist['ID'].astype(str))
    else:
        after_timestamp = int(time.time()) - (30 * 24 * 3600)

    try:
        access_token = get_access_token()
    except Exception as e:
        print(f"Erreur d'authentification Strava : {e}")
        return df_hist if not df_hist.empty else None

    headers = {'Authorization': f'Bearer {access_token}'}
    url_activities = "https://www.strava.com/api/v3/athlete/activities"
    res = requests.get(url_activities, headers=headers, params={'after': after_timestamp, 'per_page': 100})

    if res.status_code != 200:
        return df_hist if not df_hist.empty else None

    new_activities = res.json()

    if not new_activities:
        return df_hist.sort_values(by='Date_API', ascending=False)

    default_cols = ['ID', 'Date', 'Date_API', 'Type', 'Nom', 'Distance (km)', 'Dénivelé (m)', 'Temps (min)', 'FC Moyenne', 'Notes', 'FC Max']
    active_headers = sheet_headers if sheet_headers else default_cols

    nouvelles_lignes = []
    for act in new_activities:
        act_id_str = str(act['id'])

        if act_id_str not in ids_existants:
            notes = get_activity_details(act_id_str)
            valeurs_act = {
                'ID': act_id_str,
                'Date': act['start_date_local'][:10],
                'Date_API': act['start_date'],
                'Type': act['type'],
                'Nom': act['name'],
                'Distance (km)': round(act.get('distance', 0) / 1000, 2),
                'Dénivelé (m)': act.get('total_elevation_gain', 0),
                'Temps (min)': round(act.get('moving_time', 0) / 60, 1),
                'FC Moyenne': act.get('average_heartrate', 0),
                'Notes': notes,
                'FC Max': act.get('max_heartrate', 0),
            }
            nouvelles_lignes.append([valeurs_act.get(col, "") for col in active_headers])

    if nouvelles_lignes:
        ws.append_rows(nouvelles_lignes)
        df_hist = pd.DataFrame(ws.get_all_records())

    return df_hist.sort_values(by='Date_API', ascending=False)


def get_activity_details(act_id):
    """Récupère les détails complets d'une activité (incluant description et note privée)"""
    try:
        access_token = get_access_token()
        headers = {'Authorization': f'Bearer {access_token}'}
        res = requests.get(f"https://www.strava.com/api/v3/activities/{act_id}", headers=headers)
        if res.status_code == 200:
            data = res.json()
            desc = data.get('description') or ''
            priv = data.get('private_note') or ''
            if desc and priv:
                return f"{desc} | Note privée : {priv}"
            return desc or priv
    except Exception:
        pass
    return ""


def get_activity_streams(act_id):
    access_token = get_access_token()
    headers = {'Authorization': f'Bearer {access_token}'}
    url = f"https://www.strava.com/api/v3/activities/{act_id}/streams?keys=time,distance,altitude,heartrate&key_by_type=true"

    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json()
    return None


def get_advanced_kpis(act_id, fc_config=None, activity_name="", activity_type=""):
    """Calcule la répartition sur 5 zones (selon FC_max), la FC max atteinte et la dérive cardiaque."""
    streams = get_activity_streams(act_id)
    if not streams or 'heartrate' not in streams:
        return "Pas de données cardio"

    stats = compute_hr_stats_from_data(
        streams['heartrate']['data'],
        fc_config=fc_config,
        activity_name=activity_name,
        activity_type=activity_type,
    )
    if not stats:
        return "Données insuffisantes"

    b2, b3, b4, b5 = stats["boundaries"]
    tag_hi = " [HAUTE INTENSITÉ]" if stats["is_high_intensity"] else ""
    return (
        f"Cardio (FCMax réf {stats['fc_max_ref']}): Z1(<{b2}): {stats['z1']:.0f}%, "
        f"Z2({b2}-{b3}): {stats['z2']:.0f}%, Z3({b3}-{b4}): {stats['z3']:.0f}%, "
        f"Z4({b4}-{b5}): {stats['z4']:.0f}%, Z5(>={b5}): {stats['z5']:.0f}%. "
        f"FC Max séance: {stats['comparison_text']}{tag_hi}. "
        f"Dérive FC: {'+' if stats['derive'] > 0 else ''}{stats['derive']:.1f} bpm."
    )


def create_strava_activity(name, sport_type, start_date_local_iso, elapsed_time_sec, description=""):
    """Crée et publie une activité manuelle sur Strava (nécessite le scope activity:write)."""
    access_token = get_access_token()
    headers = {'Authorization': f'Bearer {access_token}'}
    payload = {
        'name': name,
        'type': sport_type,
        'sport_type': sport_type,
        'start_date_local': start_date_local_iso,
        'elapsed_time': max(60, int(elapsed_time_sec)),
        'description': description,
        'trainer': 1
    }
    res = requests.post("https://www.strava.com/api/v3/activities", headers=headers, data=payload)
    if res.status_code in (200, 201):
        return True, res.json()
    return False, f"Code {res.status_code} : {res.text}"


def exchange_code_for_tokens(auth_code):
    """Échange un code d'autorisation OAuth Strava contre un nouveau refresh_token."""
    url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code.strip(),
        'grant_type': 'authorization_code'
    }
    res = requests.post(url, data=payload)
    if res.status_code == 200:
        return True, res.json()
    return False, f"Code {res.status_code} : {res.text}"


def upload_structured_strength_activity(
    name,
    sport_type,
    start_date_local_iso,
    elapsed_time_sec,
    active_time_sec,
    total_calories,
    sets_list,
    description=""
):
    """
    Envoie une séance de renforcement vers Strava avec ses calories calculées et sa durée :
    1) Envoie un fichier TCX (data_type='tcx') incluant <Calories> et <TotalTimeSeconds>
       (les formats partenaires JSON/sets étant réservés aux clés API commerciales Strava).
    2) Met à jour le titre, sport_type (WeightTraining) et la description structurée des exercices,
       puis vérifie l'activité créée via GET /activities/{id}.
    """
    import io
    from datetime import timedelta

    access_token = get_access_token()
    headers = {'Authorization': f'Bearer {access_token}'}
    elapsed_int = max(60, int(elapsed_time_sec))
    active_int = max(1, int(active_time_sec))
    cal_int = max(1, int(round(total_calories)))

    try:
        dt_start = datetime.strptime(start_date_local_iso, "%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        dt_start = datetime.utcnow()

    def _poll_upload(up_id):
        for _ in range(7):
            time.sleep(1.5)
            check = requests.get(f"https://www.strava.com/api/v3/uploads/{up_id}", headers=headers)
            if check.status_code == 200:
                chk_data = check.json()
                if chk_data.get("error"):
                    return None, chk_data.get("error")
                act_id = chk_data.get("activity_id")
                if act_id:
                    return act_id, None
        return None, "Délai d'attente dépassé sur Strava"

    def _finaliser_et_verifier(act_id, methode_label, note_diag=""):
        try:
            requests.put(
                f"https://www.strava.com/api/v3/activities/{act_id}",
                headers=headers,
                data={'name': name, 'type': sport_type, 'sport_type': sport_type, 'description': description}
            )
        except Exception:
            pass
        details = {}
        try:
            r_get = requests.get(f"https://www.strava.com/api/v3/activities/{act_id}", headers=headers)
            if r_get.status_code == 200:
                details = r_get.json()
        except Exception:
            pass
        return True, {
            "id": act_id,
            "methode": methode_label,
            "calories_strava": details.get("calories"),
            "sport_type_strava": details.get("sport_type") or details.get("type"),
            "elapsed_time_strava": details.get("elapsed_time"),
            "nb_series_preparees": len(sets_list),
            "active_time_sec": active_int,
            "note_diag": note_diag
        }

    # --- ENVOI PRINCIPAL : FICHIER TCX AVEC CALORIES ET TEMPS ---
    dt_end = dt_start + timedelta(seconds=elapsed_int)
    t0_str = dt_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    t1_str = dt_end.strftime("%Y-%m-%dT%H:%M:%SZ")
    tcx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Other">
      <Id>{t0_str}</Id>
      <Lap StartTime="{t0_str}">
        <TotalTimeSeconds>{elapsed_int}</TotalTimeSeconds>
        <DistanceMeters>0.0</DistanceMeters>
        <Calories>{cal_int}</Calories>
        <Intensity>Active</Intensity>
        <TriggerMethod>Manual</TriggerMethod>
        <Track>
          <Trackpoint>
            <Time>{t0_str}</Time>
            <DistanceMeters>0.0</DistanceMeters>
          </Trackpoint>
          <Trackpoint>
            <Time>{t1_str}</Time>
            <DistanceMeters>0.0</DistanceMeters>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>"""
    files_tcx = {'file': ('seance_renfo.tcx', io.BytesIO(tcx_content.encode("utf-8")), 'application/xml')}
    data_tcx = {
        'data_type': 'tcx',
        'sport_type': sport_type,
        'name': name,
        'description': description,
        'trainer': 1
    }
    diag_tcx = ""
    res_tcx = requests.post("https://www.strava.com/api/v3/uploads", headers=headers, data=data_tcx, files=files_tcx)
    if res_tcx.status_code in (200, 201):
        up_tcx = res_tcx.json()
        act_id_tcx = up_tcx.get("activity_id")
        err_tcx = up_tcx.get("error")
        if not act_id_tcx and not err_tcx and up_tcx.get("id"):
            act_id_tcx, err_tcx = _poll_upload(up_tcx.get("id"))
        if act_id_tcx:
            return _finaliser_et_verifier(
                act_id_tcx,
                "Fichier TCX (Calories + Durée + Détail Exercices)",
                "Calories et durée validées par Strava via TCX"
            )
        diag_tcx = f"TCX refusé : {err_tcx}"
    elif res_tcx.status_code == 401:
        return False, f"Code 401 : {res_tcx.text}"
    else:
        diag_tcx = f"TCX HTTP {res_tcx.status_code} : {res_tcx.text}"

    # --- FALLBACK : ACTIVITÉ MANUELLE ---
    ok_man, res_man = create_strava_activity(name, sport_type, start_date_local_iso, elapsed_int, description)
    if ok_man and isinstance(res_man, dict) and res_man.get("id"):
        return _finaliser_et_verifier(res_man["id"], "Activité manuelle (/activities)", diag_tcx)
    return ok_man, res_man
