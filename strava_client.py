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
    Envoie une séance de renforcement structurée (exercices, séries, reps/durée, calories)
    via POST /api/v3/uploads (data_type='json'), puis met à jour le titre/description.
    """
    import io
    import json

    access_token = get_access_token()
    headers = {'Authorization': f'Bearer {access_token}'}

    json_payload = {
        "version": "1.0",
        "start_time": start_date_local_iso,
        "elapsed_time": max(60, int(elapsed_time_sec)),
        "active_time": max(1, int(active_time_sec)),
        "total_calories": max(1, int(round(total_calories))),
        "creator": {
            "name": "Coach Trail IA"
        },
        "sets": sets_list
    }

    json_bytes = json.dumps(json_payload, ensure_ascii=False).encode("utf-8")
    files = {
        'file': ('seance_renfo.json', io.BytesIO(json_bytes), 'application/json')
    }
    data = {
        'data_type': 'json',
        'sport_type': sport_type,
        'name': name,
        'description': description,
        'trainer': 1
    }

    res = requests.post("https://www.strava.com/api/v3/uploads", headers=headers, data=data, files=files)
    if res.status_code not in (200, 201):
        return False, f"Code {res.status_code} : {res.text}"

    upload_info = res.json()
    upload_id = upload_info.get("id")
    activity_id = upload_info.get("activity_id")

    if upload_id and not activity_id:
        for _ in range(6):
            time.sleep(1.5)
            check = requests.get(f"https://www.strava.com/api/v3/uploads/{upload_id}", headers=headers)
            if check.status_code == 200:
                chk_data = check.json()
                if chk_data.get("error"):
                    return False, f"Erreur traitement fichier Strava : {chk_data.get('error')}"
                activity_id = chk_data.get("activity_id")
                if activity_id:
                    upload_info = chk_data
                    break

    if activity_id:
        try:
            requests.put(
                f"https://www.strava.com/api/v3/activities/{activity_id}",
                headers=headers,
                data={'name': name, 'sport_type': sport_type, 'description': description}
            )
        except Exception:
            pass
        return True, {"id": activity_id, "upload_id": upload_id}

    return True, {"id": f"upload_{upload_id} (en cours de traitement sur Strava)", "upload_id": upload_id}