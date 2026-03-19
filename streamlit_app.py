import pandas as pd
import gspread
import streamlit as st
from datetime import datetime
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from st_aggrid import AgGrid, GridOptionsBuilder

# --- CONFIGURATION & CONSTANTES ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
WS_REFUS = 'REFUS'
apiKey = "" # La clé API est injectée automatiquement par l'environnement

# Liste complète des colonnes pour assurer la cohérence du Google Sheet
COLUMNS_DATA = [
    'NumReception', 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Livré le', 'Qté', 'Collection', 'Num Facture', 'StatutBL', 
    'Emplacement', 'NomDeballage', 'DateClotureDeballage', 'LitigesCompta', 
    'Commentaire_litige', 'NumTransport'
]

# Colonnes basées l'onglet REFUS
COLUMNS_REFUS = ['MAGASIN', 'Date du refus', 'Nom du fournisseur', 'Num du BL','Commentaire du refus']
				

# --- FONCTIONS TECHNIQUES ---

def authenticate_gsheet():
    """Authentification via Streamlit Secrets"""
    try:
        creds = dict(st.secrets['gspread'])
        creds['private_key'] = creds['private_key'].replace('\\n', '\n')
        return gspread.service_account_from_dict(creds)
    except Exception as e:
        st.error(f"Erreur d'authentification : {e}")
        return None

def load_data(ws_name, cols):
    """Charge les données d'un onglet spécifique"""
    try:
        gc = authenticate_gsheet()
        if not gc: return pd.DataFrame(columns=cols)
        sh = gc.open_by_key(SHEET_ID)
        
        # Vérification si l'onglet existe
        titles = [w.title for w in sh.worksheets()]
        if ws_name not in titles:
            st.error(f"❌ L'onglet '{ws_name}' est introuvable.")
            return pd.DataFrame(columns=cols)
            
        ws = sh.worksheet(ws_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty:
            return pd.DataFrame(columns=cols)
            
        # On s'assure de ne prendre que les colonnes définies
        return df.reindex(columns=cols).fillna('')
    except Exception as e:
        st.error(f"❌ Erreur de lecture {ws_name} : {e}")
        return pd.DataFrame(columns=cols)

def save_data_to_gsheet(df_updated):
    """Sauvegarde complète de la feuille (plus fiable que update_cell par cell)"""
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_DATA)
        
        # Préparation des données (headers + data)
        # Conversion des dates/objets en string pour JSON
        df_to_save = df_updated.copy()
        for col in df_to_save.columns:
            df_to_save[col] = df_to_save[col].astype(str).replace(['NaT', 'nan', 'None'], '')
            
        data_to_upload = [df_to_save.columns.values.tolist()] + df_to_save.values.tolist()
        
        ws.update('A1', data_to_upload)
        return True
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")
        return False



# --- UI : COMPOSANT GRILLE ---
def render_custom_grid(df, editable_cols=[], status_options=None):
    """Génère une grille Ag-Grid épurée avec recherche intelligente"""
    
    # Ajout d'une barre de recherche globale au-dessus de la grille
    search_term = st.text_input("🔍 Recherche rapide (Fournisseur, Numéro, etc.)", placeholder="Tapez pour filtrer...")

    gb = GridOptionsBuilder.from_dataframe(df)
    
    # Configuration par défaut épurée
    gb.configure_default_column(
        resizable=True, 
        sortable=True, 
        filterable=True, 
        editable=False,
        # On désactive le floatingFilter pour alléger visuellement
        floatingFilter=False 
    )
    
    # Configuration des colonnes éditables
    for col in editable_cols:
        if col == 'StatutBL' and status_options:
            gb.configure_column(col, editable=True, cellEditor='agSelectCellEditor', 
                               cellEditorParams={'values': status_options})
        else:
            gb.configure_column(col, editable=True)
            
        # Style subtil pour les colonnes modifiables
        gb.configure_column(col, cellStyle={'background-color': '#f8fafc', 'border-left': '3px solid #3b82f6'})

    # Formatage spécifique
    if 'Mt TTC' in df.columns:
        gb.configure_column('Mt TTC', valueFormatter="x.value + ' €'")

    gb.configure_pagination(paginationPageSize=15)
    gb.configure_selection(selection_mode="multiple", use_checkbox=True)
    
    # Intégration de la recherche globale dans les options
    grid_options = gb.build()
    if search_term:
        grid_options['quickFilterText'] = search_term
    
    return AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        theme='balham', # Thème plus compact et professionnel
        fit_columns_on_grid_load=True,
        height=500,
        allow_unsafe_jscode=True
    )

#DEF FEUILLE REFUS
def add_refus_row(row_list):
    """Ajoute réellement la ligne dans l'onglet REFUS"""
    try:
        gc = authenticate_gsheet()
        if not gc: return False
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_REFUS)
        ws.append_row(row_list)
        return True
    except Exception as e:
        st.error(f"❌ Erreur lors de l'écriture dans Google Sheets : {e}")
        return False

def send_actual_email(to_email, subject, body):
    """Envoie l'e-mail via le serveur SMTP configuré"""
    try:
        if "email" not in st.secrets:
            return False, "Configuration SMTP manquante dans les Secrets."
            
        mail_config = st.secrets["email"]
        
        msg = MIMEMultipart()
        msg['From'] = mail_config["sender_email"]
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connexion au serveur
        server = smtplib.SMTP(mail_config["smtp_server"], mail_config["smtp_port"])
        server.starttls() # Sécurisation de la connexion
        server.login(mail_config["sender_email"], mail_config["sender_password"])
        server.send_message(msg)
        server.quit()
        return True, "Succès"
    except Exception as e:
        return False, str(e)


def generate_mail_content(magasin, fournisseur, bl, commentaire):
    """Utilise Gemini pour rédiger un mail propre"""
    prompt = f"Rédige un e-mail professionnel très court pour un refus de marchandise. Magasin: {magasin}, Fournisseur: {fournisseur}, BL: {bl}, Motif: {commentaire}. Signé: L'équipe Réception."
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={apiKey}"
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except:
        return f"Madame, Monsieur,\n\nNous vous informons du refus de la livraison du fournisseur {fournisseur} ce jour au magasin de {magasin} (BL n°{bl}).\n\nMotif : {commentaire}\n\nCordialement,\nL'équipe Réception."

        

# --- APPLICATION ------------------------------------------------------------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Logistique Réception", layout="wide", page_icon="📦")

    # CSS Custom pour améliorer le look
    st.markdown("""
        <style>
        .main { background-color: #f8fafc; }
        .stButton>button { border-radius: 8px; }
        </style>
    """, unsafe_allow_html=True)
    
    if 'page' not in st.session_state: st.session_state.page = 'dashboard'

 # Menu latéral
    with st.sidebar:
        st.title("📦 Logistique")
        st.info(f"Connecté au Sheet : {WS_DATA}")
        
        pages = {
            'dashboard': "📊 Tableau de Bord",
            'refus': "🚚 Refus de marchandise ⚠️",
            'transport': "🚚 Suivi Transport",
            'pdc': "⚠️ Pas de Commande",
            'import': "📥 Import Excel",
            'emplacements': "📍 Emplacements",
            'deballage': "⚙️ Déballage",
            'litige': "⚙️ Litiges",
            'hist': "📜 Historique Global"
        }
        
        for key, label in pages.items():
            if st.button(label, use_container_width=True, type="primary" if st.session_state.page == key else "secondary"):
                st.session_state.page = key
        
        st.divider()
        if st.button("🔄 Actualiser les données"):
            st.rerun()
            
    # Chargement initial des données
    df_all = load_data(WS_DATA,COLUMNS_DATA)

    # --- PAGE ACCUEIL 
    if st.session_state.page == 'dashboard':
        st.header("📊 Tableau de Bord Réception")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Réceptions", len(df_all))
        col2.metric("À déballer", len(df_all[df_all['StatutBL'] == 'À déballer']))
        col3.metric("Litiges", len(df_all[df_all['StatutBL'] == 'LITIGE']))
        col4.metric("Terminées", len(df_all[df_all['StatutBL'].isin(['TERMINEE', 'Clôturé'])]))
        
        st.subheader("Dernières réceptions")
        st.dataframe(df_all.head(10), use_container_width=True)
    
    # --- PAGE REFUS DE MARCHANDISE---
    # --- Lié à la page REFUS  ---
    elif st.session_state.page == 'refus':
        st.header("🚚 Enregistrement d'un Refus de Marchandise")
        
        # Section Formulaire
        with st.expander("➕ Enregistrer un nouveau refus", expanded=True):
            with st.form("form_refus", clear_on_submit=True):
                col1, col2 = st.columns(2)
                f_magasin = col1.selectbox("Magasin concerne", ["BAYONNE", "PAU", "BORDEAUX", "AUTRE"])
                f_date = col1.date_input("Date du jour", datetime.now())
                f_fourn = col2.text_input("Nom du fournisseur (ex: NIKE)")
                f_bl = col2.text_input("Numero du BL")
                
                st.divider()
                f_email_dest = st.text_input("📧 Envoyer l'alerte mail à :", placeholder="exemple@domaine.com")
                f_comment = st.text_area("📝 Motif precis du refus")
                
                submitted = st.form_submit_button("✅ Valider le refus et envoyer le mail")
                
                if submitted:
                    if not f_fourn or not f_bl or not f_email_dest:
                        st.error("⚠️ Les champs Fournisseur, BL et Email sont obligatoires.")
                    else:
                        # 1. Préparation des données
                        new_row = [f_magasin, str(f_date), f_fourn, f_bl, f_comment]
                        
                        # 2. Ajout au GSheet
                        with st.spinner("Enregistrement dans le tableau..."):
                            if add_refus_row(new_row):
                                st.success("📝 Refus enregistré dans l'onglet REFUS.")
                                
                                # 3. Envoi du mail
                                with st.spinner("Rédaction et envoi du mail..."):
                                    body = generate_mail_content(f_magasin, f_fourn, f_bl, f_comment)
                                    success, msg = send_actual_email(f_email_dest, f"ALERTE REFUS : {f_fourn} ({f_magasin})", body)
                                    
                                    if success:
                                        st.balloons()
                                        st.success(f"📧 Mail envoyé avec succès à {f_email_dest}")
                                    else:
                                        st.warning(f"⚠️ Mail non envoyé : {msg}")
                        
        st.divider()
        # Section Historique (Ligne qui posait problème)
        st.subheader("📜 Historique des refus")
        df_refus = load_data(WS_REFUS, COLUMNS_REFUS)
        if not df_refus.empty:
            render_custom_grid(df_refus)
        else:
            st.info("Aucun refus enregistré pour le moment.")
    
    # --- PAGE 2 : SUIVI TRANSPORT ---
    # --- Lié à la page TRANSPORT  ---
    elif st.session_state.page == 'transport':
        st.header("🚚 Suivi des Numéros de Transport")
        # On affiche tout, avec focus sur NumTransport
        grid_res = render_custom_grid(
            df_all[['NumReception', 'Fournisseur', 'Livré le', 'NumTransport', 'StatutBL']],
            editable_cols=['NumTransport']
        )
        
        if st.button("💾 Enregistrer les modifications de transport"):
            # Fusionner les modifs avec le dataframe principal
            df_updated = df_all.copy()
            new_data = pd.DataFrame(grid_res['data'])
            for idx, row in new_data.iterrows():
                df_updated.loc[df_updated['NumReception'] == row['NumReception'], 'NumTransport'] = row['NumTransport']
            
            if save_data_to_gsheet(df_updated):
                st.success("Transports mis à jour !")
                st.rerun()


    # --- PAGE 3 : PAS DE COMMANDE ---
    # --- Lié à la page PDC  ---
    elif st.session_state.page == 'pdc':
        st.header("⚠️ Gestion des 'Pas de Commande'")
        df_all = load_data(WS_DATA, COLUMNS_DATA)
        # On filtre par exemple sur un statut spécifique ou l'absence de numéro de commande
        # Ici on affiche tout ce qui est marqué en litige ou spécifique "Sans commande"
        df_target = df_all[df_all['StatutBL'].str.contains('Commande', case=False, na=False) | (df_all['StatutBL'] == 'LITIGE')].copy()
        
        if df_target.empty:
            st.info("Aucun dossier 'Pas de Commande' identifié.")
        else:
            grid_res = render_advanced_grid(
                df_target[['NumReception', 'Fournisseur', 'StatutBL', 'Commentaire_litige', 'Date Clôture']],
                editable_cols=['StatutBL', 'Commentaire_litige', 'Date Clôture']
            )
            if st.button("💾 Actualiser les dossiers"):
                if update_multiple_rows(grid_res['data']):
                    st.success("Dossiers mis à jour.")
                    st.rerun()


    # ---  IMPORT EXCEL ---
    # --- Lié à la page DATA  ---
    elif st.session_state.page == 'import':
        st.header("📥 Import des nouvelles réceptions")
        st.write("Le fichier Excel doit contenir au minimum : `NumReception`, `Fournisseur`, `Livré le`")
        uploaded_file = st.file_uploader("Fichier Excel", type=['xlsx', 'xls'])
        
        if uploaded_file:
            df_upload = pd.read_excel(uploaded_file)
            st.write(f"Aperçu ({len(df_upload)} lignes) :")
            st.dataframe(df_upload.head())
            
            if st.button("🚀 Ajouter au Google Sheet"):
                # On prépare les données pour matcher exactement les colonnes
                df_to_append = df_upload.reindex(columns=COLUMNS_DATA).fillna('')
                # On concatène avec l'existant
                df_final = pd.concat([df_all, df_to_append], ignore_index=True)
                
                if save_data_to_gsheet(df_final):
                    st.success("Import réussi !")
                    st.rerun()

    # --- EMPLACEMENTS ---
    # --- Lié à la page DATA  ---
    elif st.session_state.page == 'emplacements':
        st.header("📍 Attribution des Emplacements")
        mask = (df_all['Emplacement'] == "") | (df_all['Emplacement'].isna())
        df_target = df_all[mask].copy()
        
        if df_target.empty:
            st.success("Toutes les réceptions ont un emplacement !")
            if st.button("Voir tout"): render_custom_grid(df_all)
        else:
            grid_res = render_custom_grid(
                df_target[['NumReception', 'Fournisseur', 'Livré le', 'Qté', 'Emplacement']],
                editable_cols=['Emplacement']
            )
            if st.button("💾 Sauvegarder les Emplacements"):
                df_updated = df_all.copy()
                new_entries = pd.DataFrame(grid_res['data'])
                for _, row in new_entries.iterrows():
                    df_updated.loc[df_updated['NumReception'] == row['NumReception'], 'Emplacement'] = row['Emplacement']
                
                if save_data_to_gsheet(df_updated):
                    st.success("Emplacements enregistrés.")
                    st.rerun()

    # --- DÉBALLAGE ---
    # --- Lié à la page DATA  ---
    elif st.session_state.page == 'deballage':
        st.header("⚙️ Suivi du Déballage ")
        # Filtrer pour ne pas montrer ce qui est déjà fini depuis longtemps si nécessaire
        df_target = df_all[df_all['StatutBL'] != 'TERMINEE'].copy()
        
        grid_res = render_custom_grid(
            df_target[['NumReception', 'Fournisseur', 'StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige']],
            editable_cols=['StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige'],
            status_options=['À déballer', 'EN COURS', 'TERMINEE', 'LITIGE', 'A_DEBALLER']
        )
        
        if st.button("💾 Enregistrer les modifications de déballage"):
            df_updated = df_all.copy()
            updated_rows = pd.DataFrame(grid_res['data'])
            for _, row in updated_rows.iterrows():
                for col in ['StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige']:
                    df_updated.loc[df_updated['NumReception'] == row['NumReception'], col] = row[col]
            
            if save_data_to_gsheet(df_updated):
                st.success("Mise à jour effectuée !")
                st.rerun()
                
    # --- PAGE 7 : LITIGES ---
    # --- Lié à la page LITIGES  ---
    elif st.session_state.page == 'litige':
        st.header("⚙️ Suivi des Litiges")
        # Filtrer pour ne pas montrer ce qui est déjà fini depuis longtemps si nécessaire
        df_target = df_all[df_all['StatutBL'] != 'TERMINEE'].copy()
        
        grid_res = render_custom_grid(
            df_target[['NumReception', 'Fournisseur', 'StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige']],
            editable_cols=['StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige'],
            status_options=['À déballer', 'EN COURS', 'TERMINEE', 'LITIGE', 'A_DEBALLER']
        )
        
        if st.button("💾 Enregistrer les modifications de déballage"):
            df_updated = df_all.copy()
            updated_rows = pd.DataFrame(grid_res['data'])
            for _, row in updated_rows.iterrows():
                for col in ['StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige']:
                    df_updated.loc[df_updated['NumReception'] == row['NumReception'], col] = row[col]
            
            if save_data_to_gsheet(df_updated):
                st.success("Mise à jour effectuée !")
                st.rerun()
    
    # --- PAGE HISTORIQUE---    
    # --- Lié à la page DATA  ---
    elif st.session_state.page == 'hist':
        st.header("📜 Historique Complet")
        render_custom_grid(df_all)

if __name__ == "__main__":
    main()
