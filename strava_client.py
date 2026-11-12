import requests
import pandas as pd
from datetime import datetime
import time
import gspread

CLIENT_ID = ""
CLIENT_SECRET = ""
REFRESH_TOKEN = ""

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
        en_tetes = ['ID', 'Date', 'Date_API', 'Type', 'Nom', 'Distance (km)', 'Dénivelé (m)', 'Temps (min)', 'FC Moyenne', 'Notes']
        ws.append_row(en_tetes)

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
        
    nouvelles_lignes = []
    for act in new_activities:
        act_id_str = str(act['id'])
        
        if act_id_str not in ids_existants:
            notes = get_activity_details(act_id_str)
            
            nouvelles_lignes.append([
                act_id_str,
                act['start_date_local'][:10],
                act['start_date'],
                act['type'],
                act['name'],
                round(act.get('distance', 0) / 1000, 2),
                act.get('total_elevation_gain', 0),
                round(act.get('moving_time', 0) / 60, 1),
                act.get('average_heartrate', 0),
                notes
            ])
        
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
    
def get_advanced_kpis(act_id):
    """Calcule la répartition sur 5 zones (FC Max 180) et la dérive cardiaque"""
    streams = get_activity_streams(act_id)
    if not streams or 'heartrate' not in streams:
        return "Pas de données cardio"
        
    hr_data = streams['heartrate']['data']
    if len(hr_data) < 10:
        return "Données insuffisantes"

    n = len(hr_data)
    z1 = sum(1 for h in hr_data if h < 108) / n * 100
    z2 = sum(1 for h in hr_data if 108 <= h < 135) / n * 100
    z3 = sum(1 for h in hr_data if 135 <= h < 153) / n * 100
    z4 = sum(1 for h in hr_data if 153 <= h < 166) / n * 100
    z5 = sum(1 for h in hr_data if h >= 166) / n * 100

    mid = n // 2
    hr_first = sum(hr_data[:mid]) / mid if mid > 0 else 0
    hr_second = sum(hr_data[mid:]) / (n - mid) if mid > 0 else 0
    derive = hr_second - hr_first

    return (
        f"Cardio (FCMax 180): Z1(<108): {z1:.0f}%, Z2(108-135): {z2:.0f}%, "
        f"Z3(135-153): {z3:.0f}%, Z4(153-166): {z4:.0f}%, Z5(>166): {z5:.0f}%. "
        f"Dérive FC: {'+' if derive > 0 else ''}{derive:.1f} bpm."
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