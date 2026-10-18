import streamlit as st
import pandas as pd
from google import genai
import strava_client
import sheets_client
import json
import time  # <--- NOUVEAU : Pour gérer les pauses (erreurs 503)
import streamlit.components.v1 as components

st.set_page_config(page_title="Coach Trail IA", page_icon="🏃‍♂️", layout="centered")

st.title("🏃‍♂️ Coach Virtuel - 60km")

# --- INITIALISATION DE L'IA ---
try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    model = 'gemini-3.8-flash'
except Exception as e:
    st.error(f"Erreur de configuration de l'IA : {e}")

# ==========================================
# SECTION 1 : SYNCHRONISATION STRAVA & BILAN
# ==========================================
st.header("📡 Données et Suivi")

# 1. On s'assure d'abord d'être connecté à Sheets (hors de la boucle conditionnelle)
sheets_client.SHEET_ID = st.secrets["SHEET_ID"]
sh = sheets_client.connect_to_sheets()

# 2. On télécharge la bibliothèque de renforcement à CHAQUE actualisation
try:
    ws_renfo = sh.worksheet("Bibliotheque_Renfo")
    st.session_state['df_renfo'] = pd.DataFrame(ws_renfo.get_all_records())
except Exception as e:
    st.session_state['df_renfo'] = pd.DataFrame()
    st.error(f"Erreur lors du téléchargement de la bibliothèque : {e}")

# 3. La boucle Strava classique (qui ne tourne qu'une fois pour éviter les appels API abusifs)
if 'strava_df' not in st.session_state:
    with st.spinner("Synchronisation avec Google Sheets et Strava..."):
        # Récupération du Plan
        ws_plan = sh.worksheet("5_Plan_4_Semaines")
        df_plan = pd.DataFrame(ws_plan.get_all_records())
        st.session_state['plan_df'] = df_plan
        st.session_state['plan_text'] = df_plan.to_markdown()

        # Synchronisation Strava cloud
        strava_client.CLIENT_ID = st.secrets["STRAVA_CLIENT_ID"]
        strava_client.CLIENT_SECRET = st.secrets["STRAVA_CLIENT_SECRET"]
        strava_client.REFRESH_TOKEN = st.secrets["STRAVA_REFRESH_TOKEN"]
        
        df_strava = strava_client.extract_training_data(sh)
        
        if df_strava is not None and not df_strava.empty:
            st.session_state['strava_df'] = df_strava
        else:
            st.warning("Aucune activité Strava trouvée.")

if 'strava_df' in st.session_state:
    df = st.session_state['strava_df']
    df_plan = st.session_state['plan_df']
    
    if st.button("🔄 Forcer l'actualisation", use_container_width=True):
        del st.session_state['strava_df']
        st.rerun()

    # --- AFFICHAGE PAR ONGLETS ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Bilan", "📈 Analyse Détaillée", "🏃‍♂️ Historique", "📅 Plan", "💪 Renforcement"])

    with tab1:
        st.subheader("Statistiques globales")
        col_dist, col_deniv, col_temps = st.columns(3)
        col_dist.metric("Distance", f"{df['Distance (km)'].sum():.1f} km")
        col_deniv.metric("Dénivelé", f"{df['Dénivelé (m)'].sum()} m")
        
        # Correction du formatage de l'heure
        temps_total = int(df['Temps (min)'].sum())
        col_temps.metric("Temps", f"{temps_total // 60}h{temps_total % 60:02d}")
        
        # NOUVEAU : Le graphique avec légende et couleur par sport
        st.bar_chart(df, x='Date', y='Distance (km)', color='Type')

    with tab2:
        st.subheader("Analyse d'une séance (Streams)")
        options = df.apply(lambda x: f"{x['Date']} - {x['Nom']} ({x['Distance (km)']} km)", axis=1).tolist()
        choix = st.selectbox("Sélectionnez une activité :", options)
        
        if choix:
            idx = options.index(choix)
            act_id = df.iloc[idx]['ID']
            
            if st.button("Télémétrie de la course"):
                with st.spinner("Téléchargement des données GPS/Cardio..."):
                    streams = strava_client.get_activity_streams(act_id)
                    if streams:
                        if 'heartrate' in streams:
                            st.write("❤️ **Fréquence Cardiaque (bpm)**")
                            st.line_chart(streams['heartrate']['data'])
                        if 'altitude' in streams:
                            st.write("⛰️ **Profil altimétrique (m)**")
                            st.line_chart(streams['altitude']['data'])
                    else:
                        st.warning("Aucune donnée détaillée disponible pour cette activité.")

    with tab3:
        st.dataframe(df, use_container_width=True, hide_index=True)

    with tab4:
        st.dataframe(df_plan, use_container_width=True, hide_index=True)

    # --- NOUVEAU : LE 5ÈME ONGLET ---
    # --- LE 5ÈME ONGLET : RENFORCEMENT ---
    with tab5:
        st.header("💪 Séances de Renforcement")

        if 'df_renfo' in st.session_state and not st.session_state['df_renfo'].empty:
            df_renfo = st.session_state['df_renfo']

            # ==========================================
            # A. LE LECTEUR INTERACTIF (PLAYER)
            # ==========================================
            if 'seance_en_cours' in st.session_state:
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
                        
                # --- NOUVEAU : LA FRISE ET L'EXERCICE SUIVANT ---
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
                
                # Affichage sur 2 colonnes : Média à gauche, Infos à droite
                col_media, col_infos = st.columns([1, 1])
                
                with col_media:
                    media_url = str(exo_actuel.get('Media_URL', ''))
                    if media_url:
                        try:
                            if media_url.endswith('.mp4'):
                                st.video(media_url)
                            else:
                                st.image(media_url, use_container_width=True)
                        except:
                            st.warning("Média introuvable.")
                            
                with col_infos:
                    st.info(f"**Consignes :**\n{exo_actuel['Description']}")
                    duree = int(exo_actuel['Duree_Defaut'])
                    
                    # --- NOUVEAU : 3 MODES DE TIMER ---
                    mode_timer = st.radio(
                        "Mode d'exécution :", 
                        ["Manuel", "Chronomètre visuel", "Automatique (avec prép.)"], 
                        horizontal=True
                    )
                    
                    if mode_timer == "Manuel":
                        st.markdown(f"⏱️ **Durée cible :** {duree} secondes")
                        
                    elif mode_timer == "Chronomètre visuel":
                        # Chronomètre classique avec bouton manuel
                        html_code = f"""
                        <div id="chrono_container" style="text-align:center; font-family:sans-serif; background-color:#f0f2f6; padding:15px; border-radius:10px;">
                            <h1 id="time" style="font-size:48px; color:#ff4b4b; margin:10px;">{duree}</h1>
                            <button onclick="startTimer()" style="padding:10px 20px; font-size:16px; cursor:pointer; border-radius:5px; border:none; background-color:#ff4b4b; color:white; font-weight:bold;">Play / Pause</button>
                        </div>
                        <script>
                            var timeLeft = {duree};
                            var timerId = null;
                            var isRunning = false;
                            function startTimer() {{
                                if(isRunning) {{
                                    clearInterval(timerId);
                                    isRunning = false;
                                }} else {{
                                    isRunning = true;
                                    timerId = setInterval(function() {{
                                        if(timeLeft <= 0) {{
                                            clearInterval(timerId);
                                            document.getElementById('time').innerHTML = "TERMINÉ !";
                                            document.getElementById('time').style.color = "#4CAF50";
                                        }} else {{
                                            document.getElementById('time').innerHTML = timeLeft;
                                            timeLeft -= 1;
                                        }}
                                    }}, 1000);
                                }}
                            }}
                        </script>
                        """
                        import streamlit.components.v1 as components
                        components.html(html_code, height=160)
                        
                    elif mode_timer == "Automatique (avec prép.)":
                        # --- LE NOUVEAU TIMER 100% AUTOMATIQUE (Prép + Effort + Suivant Auto) ---
                        prep_time = st.number_input("⏱️ Temps de préparation (sec) :", min_value=1, max_value=60, value=10)
                        
                        html_code = f"""
                        <div id="chrono_container" style="text-align:center; font-family:sans-serif; background-color:#f0f2f6; padding:15px; border-radius:10px;">
                            <h3 id="status" style="margin:0; color:#ff9800; font-size:20px;">PRÉPARATION</h3>
                            <h1 id="time" style="font-size:48px; color:#ff9800; margin:5px;">{prep_time}</h1>
                            <button onclick="toggleTimer()" style="padding:5px 15px; font-size:14px; cursor:pointer; border-radius:5px; border:none; background-color:#333; color:white;">Pause / Reprendre</button>
                        </div>
                        <script>
                            var phase = "prep"; // 'prep' ou 'work'
                            var timeLeft = {prep_time};
                            var workTime = {duree};
                            var timerId = null;
                            var isRunning = true; // Démarre automatiquement
                            
                            function updateDisplay() {{
                                if (timeLeft <= 0) {{
                                    if (phase === "prep") {{
                                        // On passe à l'effort
                                        phase = "work";
                                        timeLeft = workTime;
                                        document.getElementById('status').innerHTML = "🔥 GO GO GO !";
                                        document.getElementById('status').style.color = "#ff4b4b";
                                        document.getElementById('time').style.color = "#ff4b4b";
                                    }} else {{
                                        // Fin de l'effort
                                        clearInterval(timerId);
                                        document.getElementById('status').innerHTML = "✅ EXERCICE TERMINÉ";
                                        document.getElementById('status').style.color = "#4CAF50";
                                        document.getElementById('time').innerHTML = "0";
                                        document.getElementById('time').style.color = "#4CAF50";
                                        
                                        // --- LA MAGIE STREAMLIT : CLIC AUTOMATIQUE APRÈS 2 SECONDES ---
                                        setTimeout(function() {{
                                            var parentDoc = window.parent.document;
                                            // On cherche le bouton "Suivant"
                                            var nextBtn = parentDoc.evaluate("//button[contains(., 'Suivant ➡️')]", parentDoc, null, window.parent.XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                            if (nextBtn) {{
                                                nextBtn.click();
                                            }} else {{
                                                // Si "Suivant" n'existe pas, c'est le dernier exo, on cherche "Terminer"
                                                var finishBtn = parentDoc.evaluate("//button[contains(., '🎉 Terminer la séance')]", parentDoc, null, window.parent.XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                                if (finishBtn) {{
                                                    finishBtn.click();
                                                }}
                                            }}
                                        }}, 2000); // Pause de 2 secondes pour souffler avant le prochain exercice
                                        
                                        return;
                                    }}
                                }}
                                document.getElementById('time').innerHTML = timeLeft;
                                timeLeft -= 1;
                            }}
                            
                            function toggleTimer() {{
                                if(isRunning) {{
                                    clearInterval(timerId);
                                    isRunning = false;
                                }} else {{
                                    isRunning = true;
                                    timerId = setInterval(updateDisplay, 1000);
                                }}
                            }}
                            
                            // Lancement
                            document.getElementById('time').innerHTML = timeLeft;
                            timeLeft -= 1;
                            timerId = setInterval(updateDisplay, 1000);
                        </script>
                        """
                        import streamlit.components.v1 as components
                        components.html(html_code, height=180)
                # Navigation
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
                            st.balloons()
                            del st.session_state['seance_en_cours']
                            del st.session_state['current_exo_index']
                            time.sleep(2)
                            st.rerun()

            # ==========================================
            # B. LE MODULE DE CRÉATION
            # ==========================================
            else:
                def reset_brouillon():
                    if 'seance_brouillon' in st.session_state:
                        del st.session_state['seance_brouillon']

                # --- NOUVEAU : EXTRACTION DES TAGS MULTIPLES ---
                # Découpe les textes séparés par des virgules, enlève les espaces, et crée une liste de tags uniques
                toutes_zones = df_renfo['Zone'].astype(str).str.split(',').explode().str.strip()
                zones_dispos = sorted([z for z in toutes_zones.unique() if z != ""])

                col_mode, col_tours = st.columns([2, 1])
                with col_mode:
                    mode = st.radio(
                        "Mode de création :", 
                        ["Aléatoire Total", "Aléatoire par Zone", "Sélection Manuelle", "Constructeur par Zone"], 
                        horizontal=True,
                        on_change=reset_brouillon
                    )
                with col_tours:
                    nb_tours = st.number_input("🔄 Nombre de tours (circuits) :", min_value=1, max_value=10, value=1, on_change=reset_brouillon)
                    
                st.markdown("---")
                temps_estime = 0
                
                # 1. MODE RANDOM TOTAL
                if mode == "Aléatoire Total":
                    max_total = len(df_renfo)
                    if max_total > 1:
                        nb_exos = st.slider("Exercices par tour :", 1, max_total, min(5, max_total))
                    else:
                        st.info("💡 Un seul exercice disponible dans la base.")
                        nb_exos = 1
                        
                    if max_total > 0:
                        temps_estime = nb_exos * df_renfo['Duree_Defaut'].mean() * nb_tours
                        st.info(f"⏱️ **Aperçu Live :** ~{int(temps_estime // 60)} min {int(temps_estime % 60)} sec pour {nb_exos * nb_tours} exercices.")
                        
                        if st.button("Générer la séance"):
                            base = df_renfo.sample(n=nb_exos)
                            st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                        
                # 2. MODE RANDOM PAR ZONE
                elif mode == "Aléatoire par Zone":
                    zone_choisie = st.selectbox("Zone ciblée (Tag) :", zones_dispos)
                    
                    exos_possibles = df_renfo[df_renfo['Zone'].astype(str).str.contains(zone_choisie, case=False, na=False, regex=False)]
                    max_exos = len(exos_possibles)
                    
                    if max_exos > 1:
                        nb_exos = st.slider(f"Exercices contenant '{zone_choisie}' par tour :", 1, max_exos, min(3, max_exos))
                    elif max_exos == 1:
                        st.info(f"💡 Un seul exercice trouvé pour le tag '{zone_choisie}'. Il sera sélectionné par défaut.")
                        nb_exos = 1
                        
                    if max_exos > 0:
                        temps_estime = nb_exos * exos_possibles['Duree_Defaut'].mean() * nb_tours
                        st.info(f"⏱️ **Aperçu Live :** ~{int(temps_estime // 60)} min {int(temps_estime % 60)} sec pour {nb_exos * nb_tours} exercices.")
                        
                        if st.button("Générer la séance"):
                            base = exos_possibles.sample(n=nb_exos)
                            st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                    else:
                        st.warning("Aucun exercice trouvé pour ce tag.")
                        
                # 3. MODE MANUEL
                elif mode == "Sélection Manuelle":
                    exos_choisis = st.multiselect("Choisissez vos exercices pour 1 tour :", df_renfo['Nom'].tolist())
                    if exos_choisis:
                        temps_estime = df_renfo[df_renfo['Nom'].isin(exos_choisis)]['Duree_Defaut'].sum() * nb_tours
                        st.info(f"⏱️ **Aperçu Live :** Exactement {int(temps_estime // 60)} min {int(temps_estime % 60)} sec pour {len(exos_choisis) * nb_tours} exercices.")
                    
                    if st.button("Valider la séance") and exos_choisis:
                        base = df_renfo[df_renfo['Nom'].isin(exos_choisis)]
                        st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                        
                # 4. CONSTRUCTEUR PAR ZONE
                elif mode == "Constructeur par Zone":
                    choix_zones = {}
                    st.write("Exercices par tag (pour 1 tour) :")
                    
                    # On affiche les curseurs sur 4 colonnes pour que ce soit plus joli si vous avez beaucoup de tags
                    cols = st.columns(4) 
                    total_exos_tour = 0
                    
                    for i, zone in enumerate(zones_dispos):
                        # On filtre par "contient le tag"
                        exos_in_zone = df_renfo[df_renfo['Zone'].astype(str).str.contains(zone, case=False, na=False, regex=False)]
                        max_exos = len(exos_in_zone)
                        
                        with cols[i % 4]:
                            choix = st.number_input(f"{zone} (Max: {max_exos})", 0, max_exos, 0, key=f"zone_{zone}")
                            choix_zones[zone] = choix
                            total_exos_tour += choix
                            if choix > 0:
                                temps_estime += choix * exos_in_zone['Duree_Defaut'].mean()
                                
                    temps_estime *= nb_tours
                    if total_exos_tour > 0:
                        st.info(f"⏱️ **Aperçu Live :** ~{int(temps_estime // 60)} min {int(temps_estime % 60)} sec pour {total_exos_tour * nb_tours} exercices.")
                    
                    if st.button("Assembler la séance combinée"):
                        frames = []
                        for zone, nb in choix_zones.items():
                            if nb > 0:
                                exos_in_zone = df_renfo[df_renfo['Zone'].astype(str).str.contains(zone, case=False, na=False, regex=False)]
                                frames.append(exos_in_zone.sample(n=nb))
                        if frames:
                            # IMPORTANT : Suppression des doublons. 
                            # Si on demande 1 exo "Jambes" et 1 exo "Quadriceps", un exercice tagué "Jambes, Quadriceps" 
                            # pourrait être pioché 2 fois. Cela évite de faire le même exercice à la suite !
                            base = pd.concat(frames).drop_duplicates(subset=['Nom'])
                            
                            st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                            
                            if len(base) < total_exos_tour:
                                st.warning(f"⚠️ Pour éviter les doublons (exercices avec plusieurs tags piochés deux fois), la séance a été réduite à {len(base)} exercices distincts par tour.")

                # --- AFFICHAGE DE LA SÉANCE PRÊTE ---
                if 'seance_brouillon' in st.session_state and not st.session_state['seance_brouillon'].empty:
                    seance_prete = st.session_state['seance_brouillon']
                    st.success(f"✅ Séance prête : {len(seance_prete)} exercices (dont {nb_tours} tour(s)).")
                    
                    affichage_df = seance_prete[['Nom', 'Zone', 'Duree_Defaut', 'Description']]
                    st.dataframe(affichage_df, hide_index=True, use_container_width=True)
                    
                    if st.button("▶️ DÉMARRER L'ENTRAÎNEMENT", type="primary", use_container_width=True):
                        st.session_state['seance_en_cours'] = seance_prete
                        st.session_state['current_exo_index'] = 0
                        del st.session_state['seance_brouillon']
                        st.rerun()

        else:
            st.info("Pour activer ce module, veuillez créer l'onglet 'Bibliotheque_Renfo' dans votre Google Sheet.")
    # --- ANALYSE IA (AVEC BOUCLE ANTI-COUPURE) ---
    st.write("") 
    if st.button("🧠 Analyser ma charge d'entraînement (IA)", type="secondary", use_container_width=True):
        with st.spinner("Le coach analyse votre physiologie (téléchargement de la télémétrie)..."):
            # 1. On prend les 10 dernières pour le résumé global
            df_recent = st.session_state['strava_df'].head(10)
            
            # 2. On télécharge les streams détaillés UNIQUEMENT pour les 5 dernières
            details_avances = ""
            for index, row in df_recent.head(5).iterrows():
                kpi = strava_client.get_advanced_kpis(row['ID'])
                details_avances += f"- Course du {row['Date']} ({row['Nom']}) : {kpi}\n"
                
            prompt_analyse = f"""
            Tu es mon coach d'ultra-trail. Je prépare un 60km/4000D+ pour septembre 2027.
            
            Voici mes 10 dernières activités générales :
            {df_recent.to_markdown()}
            
            Voici l'analyse physiologique détaillée de mes 5 dernières sorties :
            {details_avances}
            
            Voici mon plan actuel :
            {st.session_state['plan_text']}
            
            Fais une analyse brève et percutante (3 points à puces max) de mon état de forme actuel.
            Concentre-toi UNIQUEMENT sur la fatigue (analyse la dérive cardiaque), l'endurance fondamentale (regarde les % de Z1), et le respect du plan. Sois direct.
            """
            
            msg_attente = st.empty()
            max_essais = 3
            
            try:
                for essai in range(max_essais):
                    try:
                        response = client.models.generate_content(model=model, contents=prompt_analyse)
                        msg_attente.empty()
                        st.info("🧠 **Diagnostic du Coach :**")
                        st.write(response.text)
                        break
                    except Exception as e:
                        # Si on a une erreur (quelle qu'elle soit : 503, disconnect, timeout...), on retente
                        if essai < max_essais - 1:
                            msg_attente.warning(f"⚠️ Instabilité réseau ({e}). Nouvelle tentative {essai + 1}/{max_essais} dans 4s...")
                            time.sleep(4)
                        else:
                            raise e
            except Exception as e:
                st.error(f"Erreur définitive : {e}")

st.divider()

# ==========================================
# SECTION 2 : COACHING & AJUSTEMENT SHEETS
# ==========================================
st.header("💬 Ajustement du Plan")

commentaires = st.text_area("Contraintes ou sensations de la semaine :", placeholder="Ex: Déplacement jeudi.")

if st.button("🤖 Générer la semaine suivante et METTRE À JOUR le Sheet", type="primary", use_container_width=True):
    if 'strava_df' not in st.session_state:
        st.error("Veuillez d'abord synchroniser vos données.")
    else:
        with st.spinner("Mise à jour du tableur en cours..."):
            strava_text = st.session_state['strava_df'].head(10).to_markdown()
            prompt_ajustement = f"""
            Tu es mon coach d'ultra-trail. Objectif 60km/4000D+ sept 2027.
            Strava :\n{strava_text}\n
            Plan :\n{st.session_state['plan_text']}\n
            Contraintes :\n{commentaires}\n
            
            Adapte la Semaine 1 du plan en respectant ma rééducation (tendon d'Achille).
            RÈGLE ABSOLUE : Formate ta réponse en JSON strict.
            Exemple exact:
            [["Semaine 1", "Reprise", "Vélo 1h", "200m", "Cheville OK."]]
            Aucun texte avant ou après le JSON.
            """
            
            # Boucle de sécurité (3 essais maximum)
            msg_attente = st.empty()
            max_essais = 3
            
            try:
                for essai in range(max_essais):
                    try:
                        response = client.models.generate_content(model=model, contents=prompt_ajustement)
                        msg_attente.empty()
                        break 
                    except Exception as e:
                        if essai < max_essais - 1:
                            msg_attente.warning(f"⚠️ Instabilité réseau ({e}). Nouvelle tentative {essai + 1}/{max_essais} dans 4s...")
                            time.sleep(4)
                        else:
                            raise e
                
                rep_texte = response.text.replace('```json', '').replace('```', '').strip()
                brut_valeurs = json.loads(rep_texte)
                
                # --- BOUCLIER ANTI-HALLUCINATION IA ---
                # 1. Si l'IA a renvoyé une liste simple au lieu d'une liste de listes
                if isinstance(brut_valeurs, list) and not isinstance(brut_valeurs[0], list):
                    brut_valeurs = [brut_valeurs]
                    
                # 2. On force strictement la première ligne, et exactement 5 colonnes
                ligne_propre = brut_valeurs[0][:5] 
                while len(ligne_propre) < 5:
                    ligne_propre.append("") # Comble les trous si l'IA a oublié une colonne
                
                nouvelles_valeurs = [ligne_propre]
                # --------------------------------------
                
                st.success("💡 Nouvelle Semaine 1 injectée :")
                st.dataframe(pd.DataFrame(nouvelles_valeurs, columns=['Période', 'Phase', 'Objectif Principal', 'Volume D+', 'Remarques']), hide_index=True)
                
                # ECRITURE SHEETS
                sheets_client.SHEET_ID = st.secrets["SHEET_ID"]
                sh = sheets_client.connect_to_sheets()
                ws_plan = sh.worksheet("5_Plan_4_Semaines")
                # Récupération de la bibliothèque de renforcement
                try:
                    ws_renfo = sh.worksheet("Bibliotheque_Renfo")
                    st.session_state['df_renfo'] = pd.DataFrame(ws_renfo.get_all_records())
                except:
                    st.session_state['df_renfo'] = pd.DataFrame() # Onglet pas encore créé
                ws_plan.update(range_name="A2:E2", values=nouvelles_valeurs)
                
                if st.button("Actualiser l'affichage"):
                    del st.session_state['plan_df']
                    st.rerun()
                    
            except json.JSONDecodeError:
                st.error("Le formatage JSON a échoué.")
                st.write(response.text)
            except Exception as e:
                st.error(f"Erreur d'écriture : {e}")
                

