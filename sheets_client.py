import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

# L'ID de votre document
SHEET_ID = "1a2fmc8DKCjYugNiZHJ5aM508lC9k53IoDwsLhplRlc8"

def connect_to_sheets():
    print("Tentative de connexion à Google Sheets...")
    try:
        # 1. On lit les identifiants depuis le coffre-fort de Streamlit
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        # 2. Définition des droits d'accès
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # 3. Authentification sécurisée (sans fichier physique)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        
        # 4. Ouverture du fichier
        # On utilise le SHEET_ID des secrets s'il existe, sinon on prend celui par défaut
        active_id = st.secrets.get("SHEET_ID", SHEET_ID)
        sh = gc.open_by_key(active_id)
        
        print(f"✅ Connexion réussie au document : '{sh.title}'")
        return sh
        
    except Exception as e:
        print("❌ Erreur de connexion :", e)
        st.error(f"Impossible de se connecter à la base de données : {e}")
        return None

# Test direct quand on lance ce fichier localement
if __name__ == "__main__":
    connect_to_sheets()