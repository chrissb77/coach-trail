import tomllib
import google.generativeai as genai

# 1. Lecture de votre clé depuis le fichier secrets
with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

genai.configure(api_key=secrets["GEMINI_API_KEY"])

# 2. Interrogation des serveurs Google
print("🔍 Modèles autorisés pour la génération de texte :")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")