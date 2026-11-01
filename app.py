import streamlit as st
import pandas as pd
from google import genai
import strava_client
import sheets_client
import json
import time
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px 

st.set_page_config(page_title="Coach Trail IA", page_icon="🏃‍♂️", layout="wide")

st.title("🏃‍♂️ Coach Virtuel - 60km")

# --- FONCTION UTILE : DÉTECTION DE LA SEMAINE EN COURS ---
def get_current_week_index(df_plan):
    try:
        today = datetime.now()
        mois_map = {"jan": 1, "fév": 2, "fev": 2, "mar": 3, "avr": 4, "mai": 5, "jui": 6, "juin": 6, "juil": 7, "aoû": 8, "aou": 8, "sep": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12}
        
        for idx, row in df_plan.iterrows():
            date_str = str(row.get('Date', ''))
            parts = date_str.split('-')
            if len(parts) == 2:
                s_parts = parts[0].strip().split()
                s_month = mois_map.get(s_parts[1].lower()[:3], today.month)
                d_start = datetime(today.year, s_month, int(s_parts[0]))
                
                e_parts = parts[1].strip().split()
                e_month = mois_map.get(e_parts[1].lower()[:3], today.month)
                d_end = datetime(today.year, e_month, int(e_parts[0]))
                
                if d_start > d_end:
                    d_end = d_end.replace(year=today.year + 1)
                
                if d_start <= today <= d_end.replace(hour=23, minute=59):
                    return idx
    except Exception:
        pass
    return 0 

# --- INITIALISATION DE L'IA ---
try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    model = 'gemini-3.8-flash' 
except Exception as e:
    st.error(f"Erreur de configuration de l'IA : {e}")

# ==========================================
# SECTION 1 : SYNCHRONISATION & DONNÉES
# ==========================================
sheets_client.SHEET_ID = st.secrets["SHEET_ID"]
sh = sheets_client.connect_to_sheets()

try:
    ws_renfo = sh.worksheet("Bibliotheque_Renfo")
    st.session_state['df_renfo'] = pd.DataFrame(ws_renfo.get_all_records())
    
    ws_progs = sh.worksheet("Programmes_Renfo")
    st.session_state['df_progs'] = pd.DataFrame(ws_progs.get_all_records())
except Exception as e:
    st.session_state['df_renfo'] = pd.DataFrame()
    st.session_state['df_progs'] = pd.DataFrame()

if 'strava_df' not in st.session_state:
    with st.spinner("Synchronisation avec Google Sheets et Strava..."):
        ws_plan = sh.worksheet("5_Plan_4_Semaines")
        df_plan = pd.DataFrame(ws_plan.get_all_records())
        st.session_state['plan_df'] = df_plan
        st.session_state['plan_text'] = df_plan.to_markdown()

        strava_client.CLIENT_ID = st.secrets["STRAVA_CLIENT_ID"]
        strava_client.CLIENT_SECRET = st.secrets["STRAVA_CLIENT_SECRET"]
        strava_client.REFRESH_TOKEN = st.secrets["STRAVA_REFRESH_TOKEN"]
        
        df_strava = strava_client.extract_training_data(sh)
        
        if df_strava is not None and not df_strava.empty:
            st.session_state['strava_df'] = df_strava
        else:
            st.warning("Aucune activité Strava trouvée.")


if 'strava_df' in st.session_state:
    df = st.session_state['strava_df'].reset_index(drop=True)
    df_plan = st.session_state['plan_df']
    
    tab_activites, tab_plan, tab_renfo = st.tabs(["📊 Activités", "📅 Plan", "💪 Renforcement"])

    # ==========================================
    # ONGLET 1 : ACTIVITÉS
    # ==========================================
    with tab_activites:
        col_titre, col_btn = st.columns([4, 1])
        with col_titre:
            st.subheader("Statistiques globales")
        with col_btn:
            if st.button("🔄 Sync Strava", use_container_width=True):
                del st.session_state['strava_df']
                st.rerun()

        col_dist, col_deniv, col_temps = st.columns(3)
        col_dist.metric("Distance Totale", f"{df['Distance (km)'].sum():.1f} km")
        col_deniv.metric("Dénivelé Total", f"{df['Dénivelé (m)'].sum()} m")
        temps_total = int(df['Temps (min)'].sum())
        col_temps.metric("Temps d'effort", f"{temps_total // 60}h{temps_total % 60:02d}")
        
        st.markdown("---")
        
        # --- GRAPH DOUBLE AXE Y (Centrage, Largeur et ID) ---
        df_graph = df.sort_values('Date', ascending=True)
        dates_uniques = df_graph['Date'].unique()
        labels_courts = [pd.to_datetime(d).strftime('%d/%m') for d in dates_uniques]
        
        fig = go.Figure()
        sports = df_graph['Type'].unique()
        couleurs = px.colors.qualitative.Plotly 
        
        for i, sport in enumerate(sports):
            df_sport = df_graph[df_graph['Type'] == sport]
            is_bike = 'ride' in sport.lower() or 'vélo' in sport.lower()
            
            fig.add_trace(go.Bar(
                x=df_sport['Date'],
                y=df_sport['Distance (km)'],
                name=sport,
                marker_color=couleurs[i % len(couleurs)],
                yaxis='y2' if is_bike else 'y',
                hovertext=df_sport['Nom'],
                customdata=df_sport['ID'], 
                offsetgroup=str(i) # Indispensable pour la largeur
            ))
            
        fig.update_layout(
            title="Volume d'entraînement par sport",
            barmode='group',
            bargap=0.05,       
            bargroupgap=0.0,   
            xaxis=dict(
                type='category',             # Force la largeur uniforme
                categoryorder='array',
                categoryarray=dates_uniques, # Garde le tri chronologique
                tickmode='array',
                tickvals=dates_uniques,      # Vraies dates pour le clic
                ticktext=labels_courts,      # Affichage court JJ/MM
                title=""
            ),
            yaxis=dict(title="Km (Course / Foot)"),
            yaxis2=dict(title="Km (Vélo)", overlaying='y', side='right', showgrid=False),
            hovermode='x unified',
            margin=dict(l=0, r=0, t=40, b=0)
        )
        
        selected_idx = 0
        try:
            event = st.plotly_chart(fig, use_container_width=True, on_select="rerun")
            if event and len(event.selection.points) > 0:
                clicked_id = event.selection.points[0].get('customdata')
                # Si Plotly renvoie l'ID dans une sous-liste, on extrait la valeur
                if isinstance(clicked_id, list):
                    clicked_id = clicked_id[0]
                # Comparaison en texte (str) sur l'index remis à zéro
                matches = df.index[df['ID'].astype(str) == str(clicked_id)].tolist()
                if matches:
                    selected_idx = matches[0]
        except Exception:
            st.plotly_chart(fig, use_container_width=True)

        # --- ANALYSE IA DE LA CHARGE ---
        st.write("") 
        if st.button("🧠 Analyser ma charge d'entraînement (IA)", type="secondary", use_container_width=True):
            with st.spinner("Le coach analyse votre physiologie (et vos notes)..."):
                # Filtre intelligent pour l'IA : on inclut les notes si elles existent
                cols_ia = ['Date', 'Nom', 'Type', 'Distance (km)', 'Dénivelé (m)']
                if 'Notes' in df.columns:
                    cols_ia.append('Notes')
                
                df_recent = df.head(10)[cols_ia]
                details_avances = ""
                for index, row in df.head(5).iterrows():
                    kpi = strava_client.get_advanced_kpis(row['ID'])
                    details_avances += f"- Course du {row['Date']} ({row['Nom']}) : {kpi}\n"
                    
                prompt_analyse = f"""
                Tu es mon coach d'ultra-trail. Je prépare un 60km/4000D+ pour septembre 2027.
                Mes 10 dernières activités (inclus mes ressentis/notes) : {df_recent.to_markdown()}
                Analyse physiologique des 5 dernières : {details_avances}
                Plan actuel : {st.session_state['plan_text']}
                Fais une analyse brève (3 points à puces max) de mon état de forme (fatigue, % Z1, respect du plan, retours de sensations).
                """
                try:
                    response = client.models.generate_content(model=model, contents=prompt_analyse)
                    st.info("🧠 **Diagnostic du Coach :**")
                    st.write(response.text)
                except Exception as e:
                    st.error(f"Erreur d'analyse : {e}")

        # --- DÉTAIL DE L'ACTIVITÉ ---
        st.markdown("---")
        options = df.apply(lambda x: f"{x['Date']} - {x['Nom']} ({x['Distance (km)']} km)", axis=1).tolist()
        choix = st.selectbox("🔎 Détail de l'activité (cliquez sur le graphe ou sélectionnez ici) :", options, index=selected_idx)
        
        if choix:
            idx = options.index(choix)
            act_id = df.iloc[idx]['ID']
            
            # 1. Récupération et affichage de la note (Sheet ou rattrapage API Strava)
            note = ""
            if 'Notes' in df.columns:
                val = df.iloc[idx]['Notes']
                if pd.notna(val) and str(val).strip().lower() not in ["", "none", "nan"]:
                    note = str(val).strip()
            
            # Si la note est vide dans le Sheet, on interroge Strava en direct pour cette activité
            if not note:
                note = strava_client.get_activity_details(act_id)
                if note:
                    # Mise à jour en mémoire
                    df.at[idx, 'Notes'] = note
                    st.session_state['strava_df'] = df
                    # Sauvegarde dans Google Sheets (Colonne J) pour ne plus avoir à la télécharger
                    try:
                        ws_hist = sh.worksheet("Historique_Strava")
                        cell = ws_hist.find(str(act_id))
                        if cell:
                            ws_hist.update_cell(cell.row, 10, note)
                    except Exception:
                        pass

            if note:
                st.info(f"📝 **Notes Strava :** {note}")
                    
            # 2. Utilisation de st.toggle pour garder le graphe ouvert en interagissant avec les cases
            if st.toggle("📈 Afficher la télémétrie détaillée (Cardio / Alti / Allure)"):
                with st.spinner("Calcul de la vitesse ajustée et génération du graphique..."):
                    streams = strava_client.get_activity_streams(act_id)
                    
                    if streams and 'distance' in streams and 'time' in streams:
                        df_s = pd.DataFrame({
                            'time': streams['time']['data'],
                            'dist': streams['distance']['data']
                        })
                        
                        # --- CALCUL DE L'ALLURE AJUSTÉE (GAP) ---
                        df_s['delta_d'] = df_s['dist'].diff().fillna(0)
                        df_s['delta_t'] = df_s['time'].diff().fillna(1)
                        
                        if 'altitude' in streams:
                            df_s['alti'] = streams['altitude']['data']
                            df_s['delta_a'] = df_s['alti'].diff().fillna(0)
                            # Règle Trail : +100m D+ = 1km plat. -100m D- = -330m plat.
                            df_s['delta_d_adj'] = df_s['delta_d'] + df_s['delta_a'].apply(lambda x: x*10 if x > 0 else x*3.3)
                        else:
                            df_s['alti'] = None
                            df_s['delta_d_adj'] = df_s['delta_d']
                            
                        # Lissage sur 30 secondes de la vitesse (m/s) pour lisser le signal GPS
                        vitesse_brute = (df_s['delta_d'] / df_s['delta_t']).rolling(30, min_periods=1).mean().clip(lower=0.08)
                        df_s['pace'] = (1000 / (vitesse_brute * 60)).clip(2, 20) # Cap entre 2:00 et 20:00 min/km
                        
                        vitesse_adj = (df_s['delta_d_adj'] / df_s['delta_t']).rolling(30, min_periods=1).mean().clip(lower=0.08)
                        df_s['gap'] = (1000 / (vitesse_adj * 60)).clip(2, 20)
                        
                        if 'heartrate' in streams:
                            df_s['hr'] = streams['heartrate']['data']
                        else:
                            df_s['hr'] = None

                        # --- CRÉATION DE L'INTERFACE GRAPHIQUE ---
                        col_opt, col_graph = st.columns([1, 4])
                        
                        with col_opt:
                            st.write("**Affichage :**")
                            show_hr = st.checkbox("❤️ Cardiaque", value=True) if df_s['hr'].notna().any() else False
                            show_alt = st.checkbox("⛰️ Altitude", value=True) if df_s['alti'].notna().any() else False
                            show_gap = st.checkbox("🏃‍♂️ Allure Ajustée (GAP)", value=False) if df_s['alti'].notna().any() else False
                            show_pace = st.checkbox("⏱️ Allure Brute", value=False)
                            
                        with col_graph:
                            fig_tel = go.Figure()
                            
                            if show_alt:
                                fig_tel.add_trace(go.Scatter(x=df_s['dist']/1000, y=df_s['alti'], fill='tozeroy', mode='none', name='Altitude (m)', fillcolor='rgba(169,169,169,0.3)', yaxis='y2'))
                            if show_pace:
                                fig_tel.add_trace(go.Scatter(x=df_s['dist']/1000, y=df_s['pace'], mode='lines', name='Allure', line=dict(color='#1f77b4', width=1, dash='dot'), yaxis='y3'))
                            if show_gap:
                                fig_tel.add_trace(go.Scatter(x=df_s['dist']/1000, y=df_s['gap'], mode='lines', name='Allure Ajustée', line=dict(color='#2ca02c', width=2), yaxis='y3'))
                            if show_hr:
                                fig_tel.add_trace(go.Scatter(x=df_s['dist']/1000, y=df_s['hr'], mode='lines', name='FC (bpm)', line=dict(color='#d62728', width=2), yaxis='y1'))

                            fig_tel.update_layout(
                                # On crée 10% d'espace vide à gauche pour éviter que les échelles Y ne se superposent
                                xaxis=dict(title="Distance (km)", domain=[0.1, 1]), 
                                yaxis=dict(title="FC (bpm)", title_font=dict(color="#d62728"), tickfont=dict(color="#d62728")),
                                yaxis2=dict(title="Altitude (m)", overlaying="y", side="right", showgrid=False),
                                # L'échelle de l'allure est inversée (autorange="reversed") pour que la vitesse grimpe vers le haut
                                yaxis3=dict(title="Allure (min/km)", overlaying="y", side="left", position=0, autorange="reversed", showgrid=False),
                                margin=dict(l=0, r=0, t=30, b=0),
                                hovermode="x unified",
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            st.plotly_chart(fig_tel, use_container_width=True)
                    else:
                        st.warning("Données GPS incomplètes pour analyser cette activité.")

        # --- HISTORIQUE ---
        st.markdown("---")
        st.subheader("Historique Complet")
        st.dataframe(df, use_container_width=True, hide_index=True)


    # ==========================================
    # ONGLET 2 : PLAN D'ENTRAÎNEMENT
    # ==========================================
    with tab_plan:
        st.header("📅 Mon Plan d'Entraînement")
        
        jours_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        jour_actuel = jours_fr[datetime.now().weekday()]
        current_week_idx = get_current_week_index(df_plan)

        for index, row in df_plan.iterrows():
            is_current = (index == current_week_idx)
            titre_semaine = f"🟢 SEMAINE EN COURS | {row.get('Semaine', '')} : {row.get('Date', '')} - Focus: {row.get('Focus', '')}" if is_current else f"{row.get('Semaine', '')} : {row.get('Date', '')} - Focus: {row.get('Focus', '')}"
            
            with st.expander(titre_semaine, expanded=is_current):
                html_content = "<div style='display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px;'>"
                for jour in jours_fr:
                    contenu = str(row.get(jour, "Repos")).replace('\n', '<br>')
                    if is_current and jour == jour_actuel:
                        border_color = "#4CAF50"
                        bg_color = "#e8f5e9"
                        titre_color = "#2e7d32"
                    else:
                        border_color = "#ddd"
                        bg_color = "#ffffff"
                        titre_color = "#333"
                        
                    html_content += "<div style='flex: 1 1 12%; min-width: 130px; background-color: " + bg_color + "; padding: 12px; border: 1px solid " + border_color + "; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);'>"
                    html_content += "<div style='color: " + titre_color + "; font-weight: bold; margin-bottom: 8px; border-bottom: 1px solid " + border_color + "; padding-bottom: 4px;'>" + jour + "</div>"
                    html_content += "<div style='font-size: 14px; color: #555;'>" + contenu + "</div>"
                    html_content += "</div>"
                    
                html_content += "</div>"
                st.write(html_content, unsafe_allow_html=True)

        st.divider()
        
        # --- AJUSTEMENT DU PLAN ---
        st.header("💬 Ajustement du Plan")
        commentaires = st.text_area("Contraintes ou sensations de la semaine :", placeholder="Ex: Déplacement jeudi.")
        
        if st.button("🤖 Générer la semaine suivante et METTRE À JOUR le Sheet", type="primary", use_container_width=True):
            date_actuelle = datetime.now().strftime("%Y-%m-%d")
            
            # Injection des notes dans le prompt si elles existent
            cols_ia = ['Date', 'Nom', 'Type', 'Distance (km)']
            if 'Notes' in df.columns:
                cols_ia.append('Notes')
            strava_text = df.head(10)[cols_ia].to_markdown()
            
            prompt_ajustement = f"""
            Tu es mon coach d'ultra-trail. Objectif 60km/4000D+ sept 2027.
            Aujourd'hui nous sommes le : {date_actuelle} (utilise cette date absolue pour comprendre "cette semaine", "demain", etc.).
            
            Strava (inclus mes notes) :\n{strava_text}\n
            Plan actuel :\n{st.session_state['plan_text']}\n
            Contraintes exceptionnelles :\n{commentaires}\n
            
            Tâche :
            1. Regarde la date d'aujourd'hui et identifie à quelle semaine du plan elle correspond.
            2. Ajuste les séances d'entraînement en respectant ma demande avec précision sur les bons jours. Prends en compte mes notes privées Strava.
            3. Renvoie la ligne complète modifiée pour cette semaine précise.
            
            RÈGLE ABSOLUE : Formate ta réponse en JSON strict avec deux clés :
            - "ligne" : un entier (2 pour Semaine 1, 3 pour Semaine 2, etc).
            - "donnees" : un tableau de 10 éléments correspondant EXACTEMENT aux colonnes (Semaine, Date, Focus, Lundi, Mardi, Mercredi, Jeudi, Vendredi, Samedi, Dimanche).
            
            Exemple exact attendu:
            {{"ligne": 4, "donnees": ["Semaine 3", "26 Oct - 1 Nov", "Endurance", "Repos", "Rehab", "Footing 45min", "Repos", "Vélotaf 1h", "Trail 2h", "Repos"]}}
            Aucun texte avant ou après le JSON.
            """
            
            with st.spinner("Analyse du calendrier et ajustement du plan en cours..."):
                try:
                    for essai in range(3):
                        try:
                            response = client.models.generate_content(model=model, contents=prompt_ajustement)
                            break 
                        except Exception as e:
                            if essai < 2:
                                time.sleep(4)
                            else:
                                raise e
                    
                    rep_texte = response.text.replace('```json', '').replace('```', '').strip()
                    brut_json = json.loads(rep_texte)
                    
                    ligne_cible = brut_json.get("ligne", 2)
                    donnees = brut_json.get("donnees", [])
                    while len(donnees) < 10:
                        donnees.append("")
                    donnees = donnees[:10] 
                    
                    ws_plan = sh.worksheet("5_Plan_4_Semaines")
                    ws_plan.update(values=[donnees], range_name=f"A{ligne_cible}:J{ligne_cible}")
                    
                    st.success(f"✅ Plan mis à jour sur la ligne {ligne_cible} !")
                    df_plan = pd.DataFrame(ws_plan.get_all_records())               
                    st.session_state['plan_df'] = df_plan                           
                    st.session_state['plan_text'] = df_plan.to_markdown()
                    
                    st.info(f"ℹ️ **Prompt envoyé à l'IA :**\n\n```text\n{prompt_ajustement}\n```")
                    
                    time.sleep(3)
                    st.rerun()
                    
                except json.JSONDecodeError:
                    st.error("❌ Le formatage JSON a échoué.")
                    st.write(response.text)
                except Exception as e:
                    st.error(f"❌ Erreur : {e}")

    # ==========================================
    # ONGLET 3 : RENFORCEMENT 
    # ==========================================
    with tab_renfo:
        st.header("💪 Séances de Renforcement")
        
        if 'df_renfo' in st.session_state and not st.session_state['df_renfo'].empty:
            df_renfo = st.session_state['df_renfo']

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
                    quantite = int(exo_actuel['Duree_Defaut'])
                    type_mesure = str(exo_actuel.get('Type_Mesure', 'Temps')).strip().lower()
                    
                    if type_mesure in ['reps', 'répétitions', 'repetitions']:
                        st.markdown(f"<div style='text-align:center; background-color:#e0f2f1; padding:20px; border-radius:10px;'><h2 style='color:#00796b; margin:0;'>🔄 À faire : {quantite} Répétitions</h2></div>", unsafe_allow_html=True)
                        st.write("")
                        st.info("Prenez le temps nécessaire pour exécuter le mouvement proprement. Cliquez sur 'Suivant' quand vous avez terminé.")
                    else:
                        mode_timer = st.radio("Mode d'exécution :", ["Manuel", "Chronomètre visuel", "Automatique (avec prép.)"], horizontal=True)
                        
                        if mode_timer == "Manuel":
                            st.markdown(f"⏱️ **Durée cible :** {quantite} secondes")
                            
                        elif mode_timer == "Chronomètre visuel":
                            html_code = f"""
                            <div id="chrono_container" style="text-align:center; background-color:#f0f2f6; padding:15px; border-radius:10px;">
                                <h1 id="time" style="font-size:48px; color:#ff4b4b; margin:10px;">{quantite}</h1>
                                <button onclick="startTimer()" style="padding:10px 20px; border-radius:5px; border:none; background-color:#ff4b4b; color:white; font-weight:bold;">Play / Pause</button>
                            </div>
                            <script>
                                var timeLeft = {quantite};
                                var timerId = null;
                                var isRunning = false;
                                function startTimer() {{
                                    if(isRunning) {{ clearInterval(timerId); isRunning = false; }} 
                                    else {{
                                        isRunning = true;
                                        timerId = setInterval(function() {{
                                            if(timeLeft <= 0) {{ clearInterval(timerId); document.getElementById('time').innerHTML = "TERMINÉ !"; document.getElementById('time').style.color = "#4CAF50"; }} 
                                            else {{ document.getElementById('time').innerHTML = timeLeft; timeLeft -= 1; }}
                                        }}, 1000);
                                    }}
                                }}
                            </script>
                            """
                            components.html(html_code, height=160)
                            
                        elif mode_timer == "Automatique (avec prép.)":
                            prep_time = st.number_input("⏱️ Préparation (sec) :", min_value=1, max_value=60, value=10)
                            html_code = f"""
                            <div id="chrono_container" style="text-align:center; background-color:#f0f2f6; padding:15px; border-radius:10px;">
                                <h3 id="status" style="margin:0; color:#ff9800;">PRÉPARATION</h3>
                                <h1 id="time" style="font-size:48px; color:#ff9800; margin:5px;">{prep_time}</h1>
                                <button onclick="toggleTimer()" style="padding:5px 15px; border-radius:5px; border:none; background-color:#333; color:white;">Pause / Reprendre</button>
                            </div>
                            <script>
                                var phase = "prep"; var timeLeft = {prep_time}; var workTime = {quantite};
                                var timerId = null; var isRunning = true;
                                function updateDisplay() {{
                                    if (timeLeft <= 0) {{
                                        if (phase === "prep") {{ phase = "work"; timeLeft = workTime; document.getElementById('status').innerHTML = "🔥 GO GO GO !"; document.getElementById('status').style.color = "#ff4b4b"; document.getElementById('time').style.color = "#ff4b4b"; }} 
                                        else {{
                                            clearInterval(timerId); document.getElementById('status').innerHTML = "✅ TERMINÉ"; document.getElementById('status').style.color = "#4CAF50"; document.getElementById('time').innerHTML = "0"; document.getElementById('time').style.color = "#4CAF50";
                                            setTimeout(function() {{
                                                var parentDoc = window.parent.document;
                                                var nextBtn = parentDoc.evaluate("//button[contains(., 'Suivant ➡️')]", parentDoc, null, window.parent.XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                                if (nextBtn) {{ nextBtn.click(); }} else {{
                                                    var finishBtn = parentDoc.evaluate("//button[contains(., '🎉 Terminer')]", parentDoc, null, window.parent.XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                                    if (finishBtn) {{ finishBtn.click(); }}
                                                }}
                                            }}, 2000); return;
                                        }}
                                    }}
                                    document.getElementById('time').innerHTML = timeLeft; timeLeft -= 1;
                                }}
                                function toggleTimer() {{ if(isRunning) {{ clearInterval(timerId); isRunning = false; }} else {{ isRunning = true; timerId = setInterval(updateDisplay, 1000); }} }}
                                document.getElementById('time').innerHTML = timeLeft; timeLeft -= 1; timerId = setInterval(updateDisplay, 1000);
                            </script>
                            """
                            components.html(html_code, height=180)
                            
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

            else:
                def reset_brouillon():
                    if 'seance_brouillon' in st.session_state:
                        del st.session_state['seance_brouillon']

                toutes_zones = df_renfo['Zone'].astype(str).str.split(',').explode().str.strip()
                zones_dispos = sorted([z for z in toutes_zones.unique() if z != ""])

                col_mode, col_tours = st.columns([2, 1])
                with col_mode:
                    mode = st.radio(
                        "Mode de création :", 
                        ["Programme Prédéfini", "Aléatoire Total", "Aléatoire par Zone", "Sélection Manuelle", "Constructeur par Zone"], 
                        horizontal=True,
                        on_change=reset_brouillon
                    )
                with col_tours:
                    nb_tours = st.number_input("🔄 Nombre de tours (circuits) :", min_value=1, max_value=10, value=1, on_change=reset_brouillon)
                    
                st.markdown("---")
                
                if mode == "Aléatoire Total":
                    max_total = len(df_renfo)
                    nb_exos = st.slider("Exercices par tour :", 1, max_total, min(5, max_total)) if max_total > 1 else 1
                    if max_total > 0 and st.button("Générer la séance"):
                        base = df_renfo.sample(n=nb_exos)
                        st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                        
                elif mode == "Aléatoire par Zone":
                    zone_choisie = st.selectbox("Zone ciblée (Tag) :", zones_dispos)
                    exos_possibles = df_renfo[df_renfo['Zone'].astype(str).str.contains(zone_choisie, case=False, na=False, regex=False)]
                    max_exos = len(exos_possibles)
                    nb_exos = st.slider(f"Exercices contenant '{zone_choisie}' par tour :", 1, max_exos, min(3, max_exos)) if max_exos > 1 else 1
                    if max_exos > 0 and st.button("Générer la séance"):
                        base = exos_possibles.sample(n=nb_exos)
                        st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                        
                elif mode == "Sélection Manuelle":
                    exos_choisis = st.multiselect("Choisissez vos exercices pour 1 tour :", df_renfo['Nom'].tolist())
                    if st.button("Valider la séance") and exos_choisis:
                        base = df_renfo[df_renfo['Nom'].isin(exos_choisis)]
                        st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                        
                elif mode == "Constructeur par Zone":
                    choix_zones = {}
                    cols = st.columns(4) 
                    for i, zone in enumerate(zones_dispos):
                        exos_in_zone = df_renfo[df_renfo['Zone'].astype(str).str.contains(zone, case=False, na=False, regex=False)]
                        max_exos = len(exos_in_zone)
                        with cols[i % 4]:
                            choix = st.number_input(f"{zone} (Max: {max_exos})", 0, max_exos, 0, key=f"zone_{zone}")
                            choix_zones[zone] = choix
                    
                    if st.button("Assembler la séance combinée"):
                        frames = []
                        for zone, nb in choix_zones.items():
                            if nb > 0:
                                exos_in_zone = df_renfo[df_renfo['Zone'].astype(str).str.contains(zone, case=False, na=False, regex=False)]
                                frames.append(exos_in_zone.sample(n=nb))
                        if frames:
                            base = pd.concat(frames).drop_duplicates(subset=['Nom'])
                            st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                
                elif mode == "Programme Prédéfini":
                    if 'df_progs' in st.session_state and not st.session_state['df_progs'].empty:
                        liste_progs = st.session_state['df_progs']['Nom_Programme'].tolist()
                        prog_choisi = st.selectbox("Choisissez votre routine :", liste_progs)
                        
                        if st.button("Charger la routine prédéfinie"):
                            exos_str = st.session_state['df_progs'].loc[st.session_state['df_progs']['Nom_Programme'] == prog_choisi, 'Exercices'].values[0]
                            liste_noms = [nom.strip() for nom in str(exos_str).split(',')]
                            exos_list = []
                            for nom in liste_noms:
                                match = df_renfo[df_renfo['Nom'].str.lower() == nom.lower()]
                                if not match.empty:
                                    exos_list.append(match.iloc[0])
                            if exos_list:
                                base = pd.DataFrame(exos_list)
                                st.session_state['seance_brouillon'] = pd.concat([base] * nb_tours, ignore_index=True)
                
                if 'seance_brouillon' in st.session_state and not st.session_state['seance_brouillon'].empty:
                    seance_prete = st.session_state['seance_brouillon']
                    st.success(f"✅ Séance prête : {len(seance_prete)} exercices.")
                    st.dataframe(seance_prete[['Nom', 'Zone', 'Duree_Defaut', 'Description']], hide_index=True, use_container_width=True)
                    if st.button("▶️ DÉMARRER L'ENTRAÎNEMENT", type="primary", use_container_width=True):
                        st.session_state['seance_en_cours'] = seance_prete
                        st.session_state['current_exo_index'] = 0
                        del st.session_state['seance_brouillon']
                        st.rerun()
        else:
            st.info("Pour activer ce module, créez l'onglet 'Bibliotheque_Renfo'.")