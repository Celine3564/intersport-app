import pandas as pd
import gspread
import streamlit as st
import io 
from datetime import datetime

# --- 1. CONFIGURATION ET CONSTANTES ---

# ID de votre Google Sheet
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk' 
WORKSHEET_NAME = 'DATA' 

KEY_COLUMN = 'NuméroAuto'
ALL_EXCEL_COLUMNS = ['Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 'Livré le', 'Qté', 'Collection']

# Colonnes manuelles réparties par étapes
APP_MANUAL_COLUMNS = [
    'StatutLivraison', 'NomTransporteur', 'Emplacement', 'NbPalettes', 'Poids_total', 
    'Commentaire_Livraison', 'LitigeReception', 'Colis_manquant/abimé/ouvert',
    'NomDeballage', 'DateDebutDeballage', 'DateFinDeballage', 'LitigesDeballe', 'Commentaire_litige',
    'PDC', 'AcheteurPDC'
]

# Définition des Vues (Colonnes visibles par étape)
STEP_1_VIEW = [KEY_COLUMN, 'Magasin', 'Fournisseur', 'Livré le', 'StatutLivraison', 'NomTransporteur', 'Emplacement', 'NbPalettes', 'Poids_total', 'LitigeReception']
STEP_1_EDIT = ['StatutLivraison', 'NomTransporteur', 'Emplacement', 'NbPalettes', 'Poids_total', 'LitigeReception']

STEP_2_VIEW = [KEY_COLUMN, 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 'Livré le', 'Qté', 'StatutLivraison']

STEP_3_VIEW = [KEY_COLUMN, 'Fournisseur', 'Livré le', 'PDC', 'AcheteurPDC', 'StatutLivraison']
STEP_3_EDIT = ['PDC', 'AcheteurPDC']

STEP_4_VIEW = [KEY_COLUMN, 'Magasin', 'Fournisseur', 'StatutLivraison', 'NomDeballage', 'DateDebutDeballage', 'DateFinDeballage', 'LitigesDeballe']
STEP_4_EDIT = ['NomDeballage', 'DateDebutDeballage', 'DateFinDeballage', 'LitigesDeballe', 'StatutLivraison']

STEP_5_VIEW = [KEY_COLUMN, 'Magasin', 'Fournisseur', 'Livré le', 'Emplacement', 'StatutLivraison', 'DateDebutDeballage']

ALL_APP_COLUMNS = list(set([KEY_COLUMN] + ALL_EXCEL_COLUMNS + APP_MANUAL_COLUMNS))

# --- 2. FONCTIONS DE GESTION GOOGLE SHEET ---

def authenticate_gsheet():
    """ Authentification sécurisée (Secrets Cloud ou fichier local credentials.json) """
    try:
        # 1. Tentative via les secrets Streamlit (Usage Cloud)
        if "gspread" in st.secrets:
            s = st.secrets["gspread"]
            return gspread.service_account_from_dict({
                "type": s["type"],
                "project_id": s["project_id"],
                "private_key_id": s["private_key_id"],
                "private_key": s["private_key"].replace('\\n', '\n'),
                "client_email": s["client_email"],
                "client_id": s["client_id"],
                "auth_uri": s["auth_uri"],
                "token_uri": s["token_uri"],
                "auth_provider_x509_cert_url": s["auth_provider_x509_cert_url"],
                "client_x509_cert_url": s["client_x509_cert_url"]
            })
        # 2. Tentative via fichier local (Usage Local)
        else:
            return gspread.service_account(filename='credentials.json')
    except Exception as e:
        st.error(f"Erreur d'authentification : {e}")
        st.info("Vérifiez que le fichier 'credentials.json' est bien présent dans votre dossier LOGISTIQUE.")
        return None

@st.cache_data(ttl=60)
def load_data_from_gsheet():
    """ Charge les données depuis Google Sheets """
    gc = authenticate_gsheet()
    if not gc: return pd.DataFrame(), []
    try:
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        headers = worksheet.row_values(1)
        
        # Nettoyage et préparation des colonnes
        if not df.empty:
            for col in ALL_APP_COLUMNS:
                if col not in df.columns: df[col] = ''
                df[col] = df[col].fillna('').astype(str).str.strip()
        
        return df, headers
    except Exception as e:
        st.error(f"Erreur lors de la lecture des données : {e}")
        return pd.DataFrame(), []

def save_changes(edited_rows, df_context, headers):
    """ Enregistre les modifications par lot pour plus de rapidité """
    if not edited_rows:
        st.warning("Aucune modification à enregistrer.")
        return

    gc = authenticate_gsheet()
    if not gc: return
    
    try:
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        # Mapping des colonnes (Nom -> Index Google Sheet)
        col_map = {name: i+1 for i, name in enumerate(headers)}
        key_idx = col_map.get(KEY_COLUMN)
        
        updates = []
        for row_idx, changes in edited_rows.items():
            # Récupérer le NuméroAuto de la ligne modifiée
            row_id = df_context.iloc[int(row_idx)][KEY_COLUMN]
            # Trouver la ligne dans la GSheet
            cell = worksheet.find(str(row_id), in_column=key_idx)
            
            if cell:
                for col_name, new_val in changes.items():
                    c_idx = col_map.get(col_name)
                    if c_idx:
                        updates.append({
                            'range': gspread.utils.rowcol_to_a1(cell.row, c_idx),
                            'values': [[str(new_val)]]
                        })
        
        if updates:
            worksheet.batch_update(updates)
            st.success(f"✅ {len(updates)} modifications enregistrées !")
            st.cache_data.clear()
            st.rerun()
            
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")

# --- 3. INTERFACE UTILISATEUR ---

def main():
    st.set_page_config(page_title="Suivi Logistique", layout="wide", page_icon="📦")

    # Initialisation de l'état de navigation
    if 'page' not in st.session_state:
        st.session_state.page = 'Accueil'

    # Barre latérale
    with st.sidebar:
        st.title("Menu Logistique")
        if st.button("🏠 Accueil", use_container_width=True): st.session_state.page = 'Accueil'
        st.divider()
        st.subheader("Étapes du flux")
        if st.button("1. Transport / Quai", use_container_width=True): st.session_state.page = 'Transport'
        if st.button("2. Import / Vue Globale", use_container_width=True): st.session_state.page = 'Import'
        if st.button("3. Saisie PDC (Achat)", use_container_width=True): st.session_state.page = 'PDC'
        if st.button("4. Déballage (Terrain)", use_container_width=True): st.session_state.page = 'Deballage'
        st.divider()
        if st.button("📊 Reste à déballer", use_container_width=True): st.session_state.page = 'Reste'

    # Chargement des données
    df, headers = load_data_from_gsheet()
    
    if df.empty:
        st.warning("En attente de connexion aux données...")
        return

    # Logique des pages
    if st.session_state.page == 'Accueil':
        st.title("Bienvenue dans l'outil de Suivi Logistique")
        st.info("Sélectionnez une étape dans le menu de gauche pour commencer la saisie.")
        
    elif st.session_state.page == 'Transport':
        st.title("🚛 1. Réception Transporteur (Quai)")
        # Filtre rapide
        search = st.text_input("Filtrer par Fournisseur ou N° Auto", "")
        df_f = df[df.apply(lambda row: search.lower() in row.astype(str).str.lower().values, axis=1)]
        
        if st.button("💾 Enregistrer les modifications de Transport"):
            save_changes(st.session_state.edit_transport.get("edited_rows"), df_f, headers)
            
        st.data_editor(
            df_f[STEP_1_VIEW],
            key="edit_transport",
            use_container_width=True,
            hide_index=True,
            column_config={c: st.column_config.Column(disabled=(c not in STEP_1_EDIT)) for c in STEP_1_VIEW}
        )

    elif st.session_state.page == 'Import':
        st.title("📥 2. Vue Globale de l'Import")
        st.dataframe(df[STEP_2_VIEW], use_container_width=True, hide_index=True)

    elif st.session_state.page == 'PDC':
        st.title("💳 3. Saisie des PDC (Achat)")
        if st.button("💾 Enregistrer PDC"):
            save_changes(st.session_state.edit_pdc.get("edited_rows"), df, headers)
            
        st.data_editor(
            df[STEP_3_VIEW],
            key="edit_pdc",
            use_container_width=True,
            hide_index=True,
            column_config={c: st.column_config.Column(disabled=(c not in STEP_3_EDIT)) for c in STEP_3_VIEW}
        )

    elif st.session_state.page == 'Deballage':
        st.title("📦 4. Déballage & Litiges")
        if st.button("💾 Enregistrer Déballage"):
            save_changes(st.session_state.edit_deb.get("edited_rows"), df, headers)
            
        st.data_editor(
            df[STEP_4_VIEW],
            key="edit_deb",
            use_container_width=True,
            hide_index=True,
            column_config={c: st.column_config.Column(disabled=(c not in STEP_4_EDIT)) for c in STEP_4_VIEW}
        )

    elif st.session_state.page == 'Reste':
        st.title("📊 5. Reste à déballer")
        # Filtrage des lignes où le déballage n'est pas fini
        df_reste = df[(df['StatutLivraison'].str.upper() != 'TERMINÉ') & (df['DateFinDeballage'] == '')]
        st.metric("Commandes en attente", len(df_reste))
        st.table(df_reste[STEP_5_VIEW])

if __name__ == "__main__":
    main()
