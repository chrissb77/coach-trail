import gspread

# Remplacez ceci par l'ID que vous avez copié dans l'URL de votre document
SHEET_ID = "1a2fmc8DKCjYugNiZHJ5aM508lC9k53IoDwsLhplRlc8"

def connect_to_sheets():
    print("Tentative de connexion à Google Sheets...")
    try:
        # Authentification via votre fichier JSON de service
        gc = gspread.service_account(filename="service_account.json")
        
        # Ouverture du fichier
        sh = gc.open_by_key(SHEET_ID)
        print(f"✅ Connexion réussie au document : '{sh.title}'")
        
        # Test de lecture sur le premier onglet (Progression Annuelle)
        worksheet = sh.sheet1
        
        # On récupère toutes les valeurs
        valeurs = worksheet.get_all_values()
        
        print("\nVoici les en-têtes de votre tableur :")
        print(valeurs[0])
        
        return sh
        
    except FileNotFoundError:
        print("❌ Erreur : Le fichier 'service_account.json' est introuvable dans le dossier.")
    except Exception as e:
        print("❌ Erreur de connexion :", e)
        print("Avez-vous bien partagé le document avec l'adresse email du compte de service ?")
        return None

# Test direct quand on lance ce fichier
if __name__ == "__main__":
    connect_to_sheets()