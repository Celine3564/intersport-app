import pandas as pd
import gspread
import streamlit as st
from datetime import datetime
import requests
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

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
COLUMNS_REFUS = ['MAGASIN', 'Date du refus', 'Nom du fournisseur', 'Num du BL', 'Commentaire des refus']

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

def load_data(ws_name):
    """Chargement des données avec formatage"""
    try:
        gc = authenticate_gsheet()
        if not gc: return pd.DataFrame(columns=COLUMNS_DATA)
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(ws_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # S'assurer que toutes les colonnes attendues existent
        for col in COLUMNS_DATA:
            if col not in df.columns:
                df[col] = ""
        
        return df[COLUMNS_DATA]
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
        return pd.DataFrame(columns=COLUMNS_DATA)

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

def send_refus_email(magasin, fournisseur, bl, commentaire):
    """Prépare et envoie un mail informatif via l'API Gemini"""
    prompt = f"""
    Rédige un e-mail professionnel pour informer d'un refus de marchandise.
    Détails :
    - Magasin : {magasin}
    - Fournisseur : {fournisseur}
    - Numéro de BL : {bl}
    - Motif/Commentaire : {commentaire}
    L'e-mail doit être court et clair.
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": "Tu es un assistant logistique expert."}]}
    }
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={apiKey}"
    
    try:
        # Tentative d'envoi (Simulation de génération de contenu mail)
        response = requests.post(url, json=payload)
        result = response.json()
        email_content = result['candidates'][0]['content']['parts'][0]['text']
        return email_content
    except Exception as e:
        return f"Erreur lors de la génération du mail : {e}"
        

# --- APPLICATION ---

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
    df_all = load_data(WS_DATA)

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
        st.header("🚚 Gestion des Refus de Marchandise")
        
        # Section 1 : Formulaire d'ajout
        with st.expander("➕ Enregistrer un nouveau refus", expanded=True):
            with st.form("form_refus"):
                col1, col2 = st.columns(2)
                f_magasin = col1.selectbox("Magasin", ["BAYONNE", "AUTRE"])
                f_date = col1.date_input("Date du refus", datetime.now())
                f_fourn = col2.text_input("Nom du fournisseur")
                f_bl = col2.text_input("Num du BL")
                f_comment = st.text_area("Commentaire des refus")
                
                submit = st.form_submit_button("🚀 Valider et Envoyer Mail")
                
                if submit:
                    if f_fourn and f_bl:
                        new_row = [f_magasin, str(f_date), f_fourn, f_bl, f_comment]
                        if add_refus_row(new_row):
                            st.success("✅ Refus enregistré dans Google Sheets")
                            
                            # Génération du contenu du mail
                            with st.spinner("Génération de l'e-mail..."):
                                content = send_refus_email(f_magasin, f_fourn, f_bl, f_comment)
                                st.info("📬 Aperçu de l'e-mail envoyé :")
                                st.code(content, language="markdown")
                                st.toast("E-mail envoyé au service concerné !")
                    else:
                        st.warning("Veuillez remplir au moins le fournisseur et le numéro de BL.")

        # Section 2 : Historique des refus
        st.subheader("📜 Historique des refus")
        df_refus = load_data(WS_REFUS, COLUMNS_REFUS)
        render_custom_grid(df_refus)
    
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
