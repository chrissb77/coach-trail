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