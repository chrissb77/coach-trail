import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SHEET_ID = "1a2fmc8DKCjYugNiZHJ5aM508lC9k53IoDwsLhplRlc8"

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