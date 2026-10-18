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
        en_tetes = ['ID', 'Date', 'Date_API', 'Type', 'Nom', 'Distance (km)', 'Dénivelé (m)', 'Temps (min)', 'FC Moyenne']
        ws.append_row(en_tetes)

    donnees = ws.get_all_records()
    df_hist = pd.DataFrame(donnees)
    
    ids_existants = set() # NOUVEAU : Mémoire des IDs existants
    
    if not df_hist.empty:
        last_date_str = df_hist['Date_API'].max()
        dt_obj = datetime.strptime(last_date_str, "%Y-%m-%dT%H:%M:%SZ")
        after_timestamp = int(dt_obj.timestamp())
        # On convertit les ID existants en texte pour les comparer facilement
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
        
        # NOUVEAU : Filtre strict, on n'ajoute que si l'ID n'est pas dans le Sheet
        if act_id_str not in ids_existants:
            nouvelles_lignes.append([
                act_id_str,
                act['start_date_local'][:10],
                act['start_date'],
                act['type'],
                act['name'],
                round(act.get('distance', 0) / 1000, 2),
                act.get('total_elevation_gain', 0),
                round(act.get('moving_time', 0) / 60, 1),
                act.get('average_heartrate', 0)
            ])
        
    if nouvelles_lignes:
        ws.append_rows(nouvelles_lignes)
        df_hist = pd.DataFrame(ws.get_all_records())
        
    return df_hist.sort_values(by='Date_API', ascending=False)

def get_activity_streams(act_id):
    access_token = get_access_token()
    headers = {'Authorization': f'Bearer {access_token}'}
    url = f"https://www.strava.com/api/v3/activities/{act_id}/streams?keys=time,distance,altitude,heartrate&key_by_type=true"
    
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json()
    return None
    
def get_advanced_kpis(act_id):
    """Calcule des indicateurs physiologiques avancés à partir des streams"""
    streams = get_activity_streams(act_id)
    if not streams or 'heartrate' not in streams:
        return "Pas de données cardio"
        
    hr_data = streams['heartrate']['data']
    if len(hr_data) < 10:
        return "Données insuffisantes"

    # 1. Calcul du temps passé par zone (Seuils arbitraires à adapter : 140 et 160)
    z1 = sum(1 for h in hr_data if h < 140) / len(hr_data) * 100
    z2 = sum(1 for h in hr_data if 140 <= h <= 160) / len(hr_data) * 100
    z3 = sum(1 for h in hr_data if h > 160) / len(hr_data) * 100

    # 2. Détection de la dérive cardiaque (Fatigue / Déshydratation)
    mid = len(hr_data) // 2
    hr_first = sum(hr_data[:mid]) / mid if mid > 0 else 0
    hr_second = sum(hr_data[mid:]) / (len(hr_data)-mid) if mid > 0 else 0
    derive = hr_second - hr_first

    return f"Cardio: {z1:.0f}% en Z1(Aérobie), {z2:.0f}% en Z2(Seuil), {z3:.0f}% en Z3(Intense). Dérive FC: {'+' if derive > 0 else ''}{derive:.1f} bpm entre le début et la fin."