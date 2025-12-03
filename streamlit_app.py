import pandas as pd
import gspread
import streamlit as st
import io 
from datetime import datetime

# --- 1. CONFIGURATION ET CONSTANTES ---

# --- CONSTANTES GSPREAD ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk' 
WORKSHEET_NAME = 'DATA' 
PENDING_BL_WORKSHEET_NAME = 'BL_EN_ATTENTE' 
PDC_WORKSHEET_NAME = 'PDC' # Nouvelle feuille pour l'étape 5

# --- DÉFINITION DES COLONNES PAR ÉTAPE ---

KEY_COLUMN = 'NuméroAuto'

# Colonnes provenant de l'Excel (Source de vérité, Lecture Seule)
ALL_EXCEL_COLUMNS = [
    'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Livré le', 'Qté', 'Collection'
]

# Colonnes Manuelles (Saisies par l'utilisateur dans l'App)
APP_MANUAL_COLUMNS = [
    'StatutLivraison', 
    'NomTransporteur', 'Emplacement', 'NbPalettes', 'Poids_total', 
    'Commentaire_Livraison', 'LitigeReception', 'Colis_manquant/abimé/ouvert',
    'NomDeballage', 'DateDebutDeballage', 'LitigesDeballe', 'Commentaire_litige'
    
]

# --- DEFINITION DES VUES ---

# Étape 1 : Affichage Uniquement
STEP_1_VIEW_COLUMNS = [
    KEY_COLUMN, 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Livré le', 'Qté', 'Collection', 'StatutLivraison'
]

# Étape 2 : Saisie Transport
STEP_2_VIEW_COLUMNS = [
    KEY_COLUMN, 'Magasin', 'Fournisseur', 'Livré le', 'Qté', 
    'Collection', 'StatutLivraison', 
    'NomTransporteur', 'Emplacement', 'NbPalettes', 'Poids_total', 
    'Commentaire_Livraison', 'LitigeReception', 'Colis_manquant/abimé/ouvert'
]
STEP_2_EDITABLE = [
    'StatutLivraison', 'NomTransporteur', 'Emplacement', 'NbPalettes', 
    'Poids_total', 'Commentaire_Livraison', 'LitigeReception', 'Colis_manquant/abimé/ouvert'
]

# Étape 3 : Saisie Déballage
STEP_3_VIEW_COLUMNS = [
    KEY_COLUMN, 'Magasin', 'Fournisseur', 'Livré le', 'Qté', 
    'Collection', 'StatutLivraison', 
    'NomDeballage', 'DateDebutDeballage', 'LitigesDeballe', 'Commentaire_litige'
]
STEP_3_EDITABLE = [
    'NomDeballage', 'DateDebutDeballage', 'LitigesDeballe', 'Commentaire_litige'
]

# Union de toutes les colonnes
ALL_APP_COLUMNS = list(set([KEY_COLUMN] + ALL_EXCEL_COLUMNS + APP_MANUAL_COLUMNS))

# Colonnes pour les BLs en attente (Étape 4)
PENDING_BL_COLUMNS = ['Fournisseur', 'NuméroBL', 'DateReceptionPhysique', 'Statut']

# Colonnes pour les PDC (Étape 5) - Nouvelle structure
PDC_COLUMNS = ['Fournisseur', 'NuméroBL', 'DateReceptionPhysique', 'Acheteur', 'mail acheteur', 'date relance', 'Nombre de relance']

# Colonnes requises pour le fichier d'importation
IMPORT_REQUIRED_COLUMNS = [KEY_COLUMN, 'Magasin', 'Fournisseur', 'Mt TTC'] 

# Liste de toutes les colonnes de la feuille
SHEET_REQUIRED_COLUMNS = ALL_APP_COLUMNS + ['Clôturé']


# --- 2. FONCTIONS DE GESTION GOOGLE SHEET ---

def authenticate_gsheet():
    """Authentifie et retourne l'objet gspread Client."""
    secrets_immutable = st.secrets['gspread']
    creds_for_auth = dict(secrets_immutable)
    
    REQUIRED_KEYS = ['private_key', 'client_email', 'project_id', 'type']
    for key in REQUIRED_KEYS:
        if key not in creds_for_auth or not creds_for_auth[key]:
            raise ValueError(f"Erreur de configuration : Le secret '{key}' est manquant ou vide.")

    private_key_value = str(creds_for_auth['private_key']).strip()
    cleaned_private_key = private_key_value.replace('\\n', '\n')
    
    json_key_content = {
        "type": creds_for_auth['type'],
        "project_id": creds_for_auth['project_id'],
        "private_key": cleaned_private_key,
        "client_email": creds_for_auth['client_email'],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": creds_for_auth.get('client_x509_cert_url', '')
    }
    
    return gspread.service_account_from_dict(json_key_content)

@st.cache_data(ttl=600) 
def load_data_from_gsheet():
    """ 
    Lit la Google Sheet et retourne un DataFrame avec les commandes ouvertes.
    """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        with st.spinner('Chargement des données de Google Sheets...'):
            df_full = pd.DataFrame(worksheet.get_all_records())
            sheet_values = worksheet.get_all_values()
            column_headers = sheet_values[0] if sheet_values else []

        df_full.columns = df_full.columns.str.strip()
        
        # Validation minimale
        if KEY_COLUMN not in df_full.columns:
             st.error(f"Colonne essentielle '{KEY_COLUMN}' manquante dans la Google Sheet.")
             return pd.DataFrame(), []
        
        # Typage de base
        df_full[KEY_COLUMN] = df_full[KEY_COLUMN].astype(str).str.strip()
        
        if 'Clôturé' in df_full.columns:
            df_full['Clôturé'] = df_full['Clôturé'].astype(str).str.strip().str.upper()
            df_open = df_full[df_full['Clôturé'] != 'OUI'].copy()
        else:
            df_open = df_full.copy()

        # Garantir que toutes les colonnes manuelles possibles sont présentes et de type string
        for col in ALL_APP_COLUMNS:
            if col in df_open.columns:
                df_open[col] = df_open[col].fillna('').astype(str).str.strip()
            else:
                df_open[col] = '' # Créer la colonne vide si elle n'existe pas encore
            
        df_open = df_open.sort_values(by=KEY_COLUMN, ascending=True).reset_index(drop=True)
        
        st.success(f"Données chargées : {len(df_open)} commandes ouvertes prêtes.")
        return df_open, column_headers

    except Exception as e:
        st.error(f"Erreur de chargement. Vérifiez les secrets/permissions. Erreur: {e}")
        return pd.DataFrame(), []

@st.cache_data(ttl=300)
def get_all_existing_ids(column_headers):
    """ Récupère tous les NuméroAuto existants dans la Google Sheet (même Clôturés). """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)

        try:
            key_col_index = column_headers.index(KEY_COLUMN) + 1 
        except ValueError:
            return set()

        all_ids = worksheet.col_values(key_col_index)[1:] 
        return set(str(id).strip() for id in all_ids if id)
        
    except Exception as e:
        st.error(f"Erreur lors de la récupération des IDs existants: {e}")
        return set()

def save_data_to_gsheet(edited_df, df_filtered_pre_edit, column_headers):
    """
    Sauvegarde les données éditées par l'utilisateur dans la Google Sheet via batch_update.
    """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        edited_rows = st.session_state["command_editor"]["edited_rows"]
        
        if not edited_rows:
            st.warning("Aucune modification détectée dans le tableau.")
            return

        updates = []
        
        col_to_index = {header.strip(): i + 1 for i, header in enumerate(column_headers)}
        key_col_index = col_to_index.get(KEY_COLUMN)
        
        if not key_col_index:
            st.error(f"Colonne clé '{KEY_COLUMN}' introuvable dans la feuille Google. Sauvegarde annulée.")
            return

        for filtered_index, changes in edited_rows.items():
            key_value = df_filtered_pre_edit.iloc[filtered_index][KEY_COLUMN]
            cell = worksheet.find(str(key_value), in_column=key_col_index)
            
            if cell is None:
                st.error(f"Clé '{key_value}' introuvable. Ligne non sauvegardée.")
                continue
                
            physical_row = cell.row
            
            for col_name, new_value in changes.items():
                col_index = col_to_index.get(col_name)
                if col_index is None:
                    # Si la colonne n'existe pas dans la GSheet, on l'ignore (ou on pourrait l'ajouter)
                    continue
                updates.append({
                    'range': gspread.utils.rowcol_to_a1(physical_row, col_index),
                    'values': [[str(new_value)]] 
                })

        if updates:
            worksheet.batch_update(updates)
            st.success(f"💾 {len(edited_rows)} ligne(s) mise(s) à jour avec succès!")
            st.cache_data.clear()
            get_all_existing_ids.clear()
            st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde des données : {e}")

def upload_new_receptions(uploaded_file, column_headers):
    """ Lit un fichier Excel et ajoute les nouvelles réceptions à la Google Sheet. """
    if uploaded_file is None: return

    try:
        df_new = pd.read_excel(uploaded_file, engine='openpyxl')
        df_new.columns = df_new.columns.str.strip()
        
        missing_cols = [col for col in IMPORT_REQUIRED_COLUMNS if col not in df_new.columns]
        if missing_cols:
            st.error(f"Fichier Excel incomplet. Colonnes manquantes : {', '.join(missing_cols)}")
            return
            
        df_new[KEY_COLUMN] = df_new[KEY_COLUMN].astype(str).str.strip()
        
        internal_duplicates = df_new[df_new.duplicated(subset=[KEY_COLUMN], keep=False)][KEY_COLUMN].unique()
        if len(internal_duplicates) > 0:
            st.warning(f"⚠️ {len(internal_duplicates)} NuméroAuto en doublon dans le fichier. Ignorés.")
        df_unique_to_check = df_new.drop_duplicates(subset=[KEY_COLUMN], keep='first')
        
        existing_ids = get_all_existing_ids(column_headers)
        external_duplicates = df_unique_to_check[df_unique_to_check[KEY_COLUMN].isin(existing_ids)][KEY_COLUMN].tolist()
        
        if len(external_duplicates) > 0:
            st.error(f"❌ {len(external_duplicates)} NuméroAuto déjà présents en base.")
        
        df_to_append = df_unique_to_check[~df_unique_to_check[KEY_COLUMN].isin(existing_ids)].copy()
        
        if df_to_append.empty:
            st.warning("Aucune nouvelle ligne unique à importer.")
            return

        df_insert = df_to_append.copy()
        for col in column_headers:
            if col not in df_insert.columns:
                if col == 'Clôturé': df_insert[col] = 'NON' 
                elif col == 'PDC': df_insert[col] = 'NON'
                else: df_insert[col] = ''
        
        df_insert = df_insert.reindex(columns=column_headers).fillna('').astype(str)
        data_to_append = df_insert.values.tolist()
        
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        worksheet.append_rows(data_to_append, value_input_option='USER_ENTERED')
        
        st.success(f"✅ **{len(data_to_append)}** nouvelle(s) réception(s) importée(s)!")
        st.session_state.uploader_key += 1 
        st.cache_data.clear()
        get_all_existing_ids.clear()
        st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de l'importation : {e}")

# --- FONCTIONS POUR L'Étape 4 (BL en attente) ---
@st.cache_data(ttl=60)
def load_non_saisie_data():
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        try:
            worksheet = sh.worksheet(PENDING_BL_WORKSHEET_NAME)
        except gspread.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=PENDING_BL_WORKSHEET_NAME, rows=1, cols=len(PENDING_BL_COLUMNS))
            worksheet.append_row(PENDING_BL_COLUMNS)
            return pd.DataFrame(columns=PENDING_BL_COLUMNS)

        with st.spinner(f'Chargement des BLs en attente...'):
            df = pd.DataFrame(worksheet.get_all_records())
        
        df = df.reindex(columns=PENDING_BL_COLUMNS)
        if 'DateReceptionPhysique' in df.columns:
            df['DateReceptionPhysique'] = pd.to_datetime(df['DateReceptionPhysique'], errors='coerce')
            df = df.sort_values(by='DateReceptionPhysique', ascending=False)
            
        for col in PENDING_BL_COLUMNS:
            if col != 'DateReceptionPhysique' and col in df.columns:
                df[col] = df[col].fillna('').astype(str)
        return df
    except Exception as e:
        st.error(f"Erreur chargement BLs : {e}")
        return pd.DataFrame(columns=PENDING_BL_COLUMNS)

def save_pending_bl_updates(df_current, deleted_rows):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(PENDING_BL_WORKSHEET_NAME)
        df_final = df_current.drop(deleted_rows).reset_index(drop=True)
        if 'DateReceptionPhysique' in df_final.columns:
             df_final['DateReceptionPhysique'] = df_final['DateReceptionPhysique'].dt.strftime('%Y-%m-%d').fillna('')
        data_to_save = [PENDING_BL_COLUMNS] + df_final.values.tolist()
        worksheet.clear()
        worksheet.update('A1', data_to_save)
        st.success(f"🗑️ Mise à jour effectuée.")
        st.cache_data.clear()
        load_non_saisie_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Erreur maj BLs : {e}")

def add_pending_bl(fournisseur, numero_bl):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(PENDING_BL_WORKSHEET_NAME)
        new_row = {
            'Fournisseur': fournisseur,
            'NuméroBL': numero_bl,
            'DateReceptionPhysique': datetime.now().strftime('%Y-%m-%d'),
            'Statut': 'à saisir'
        }
        data_to_append = [[new_row.get(col, '') for col in PENDING_BL_COLUMNS]]
        worksheet.append_rows(data_to_append, value_input_option='USER_ENTERED')
        st.success(f"✅ BL '{numero_bl}' ajouté.")
        load_non_saisie_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Erreur ajout BL : {e}")

# --- FONCTIONS POUR L'Étape 5 (PDC) ---
@st.cache_data(ttl=60)
def load_pdc_data():
    """ 
    Lit la feuille Google 'PDC' et retourne un DataFrame.
    """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        
        try:
            worksheet = sh.worksheet(PDC_WORKSHEET_NAME)
        except gspread.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=PDC_WORKSHEET_NAME, rows=1, cols=len(PDC_COLUMNS))
            worksheet.append_row(PDC_COLUMNS)
            return pd.DataFrame(columns=PDC_COLUMNS)

        with st.spinner(f'Chargement des PDC...'):
            df = pd.DataFrame(worksheet.get_all_records())
        
        df = df.reindex(columns=PDC_COLUMNS)
        
        # Gestion des dates
        if 'DateReceptionPhysique' in df.columns:
            df['DateReceptionPhysique'] = pd.to_datetime(df['DateReceptionPhysique'], errors='coerce')
        if 'date relance' in df.columns:
            df['date relance'] = pd.to_datetime(df['date relance'], errors='coerce')
            
        # Tri par date de réception
        if 'DateReceptionPhysique' in df.columns:
            df = df.sort_values(by='DateReceptionPhysique', ascending=False)
            
        # Conversion string pour les autres
        for col in PDC_COLUMNS:
            if col not in ['DateReceptionPhysique', 'date relance'] and col in df.columns:
                df[col] = df[col].fillna('').astype(str)
                
        return df

    except Exception as e:
        st.error(f"Erreur de chargement des PDC. Erreur: {e}")
        return pd.DataFrame(columns=PDC_COLUMNS)

def add_pdc_entry(fournisseur, numero_bl, date_reception, acheteur, mail_acheteur, date_relance, nb_relance):
    """ Ajoute manuellement une nouvelle entrée dans la feuille PDC. """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(PDC_WORKSHEET_NAME)

        new_row = {
            'Fournisseur': fournisseur,
            'NuméroBL': numero_bl,
            'DateReceptionPhysique': date_reception.strftime('%Y-%m-%d') if date_reception else '',
            'Acheteur': acheteur,
            'mail acheteur': mail_acheteur,
            'date relance': date_relance.strftime('%Y-%m-%d') if date_relance else '',
            'Nombre de relance': str(nb_relance)
        }
        
        data_to_append = [[new_row.get(col, '') for col in PDC_COLUMNS]]
        worksheet.append_rows(data_to_append, value_input_option='USER_ENTERED')
        
        st.success(f"✅ PDC '{numero_bl}' ajouté.")
        load_pdc_data.clear() 
        st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de l'ajout PDC : {e}")

def save_pdc_updates(df_current, deleted_rows):
    """
    Met à jour la feuille PDC en supprimant les lignes cochées.
    """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(PDC_WORKSHEET_NAME)
        
        df_final = df_current.drop(deleted_rows).reset_index(drop=True)

        # Formatage des dates pour l'écriture
        if 'DateReceptionPhysique' in df_final.columns:
             df_final['DateReceptionPhysique'] = df_final['DateReceptionPhysique'].dt.strftime('%Y-%m-%d').fillna('')
        if 'date relance' in df_final.columns:
             df_final['date relance'] = df_final['date relance'].dt.strftime('%Y-%m-%d').fillna('')

        data_to_save = [PDC_COLUMNS] + df_final.values.tolist()
        worksheet.clear()
        worksheet.update('A1', data_to_save)
        
        st.success(f"🗑️ Mise à jour PDC effectuée.")
        st.cache_data.clear()
        load_pdc_data.clear() 
        st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de la mise à jour des PDC : {e}")


# --- UI HELPER ---
def display_data_editor(df_filtered, view_cols, editable_cols):
    """ Affiche l'éditeur avec les colonnes de vue et la config d'édition. """
    
    column_configs = {
        col: st.column_config.Column(
            col,
            disabled=(col not in editable_cols)
        ) for col in view_cols
    }
    
    cols_to_show = [c for c in view_cols if c in df_filtered.columns]
    df_to_show = df_filtered[cols_to_show].copy()

    st.session_state['df_filtered_pre_edit'] = df_filtered.copy()

    edited_df = st.data_editor(
        df_to_show, 
        key="command_editor",
        height=500,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_order=cols_to_show,
        column_config=column_configs,
    )
    return edited_df

def display_details(df_filtered, view_cols):
    selection_state = st.session_state.get("command_editor", {}).get("selection", {})
    selected_rows_indices = selection_state.get("rows", [])
    
    if selected_rows_indices and not df_filtered.empty:
        selected_index = selected_rows_indices[0]
        try:
            key_value = df_filtered.iloc[selected_index][KEY_COLUMN]
            selected_row_data = df_filtered[df_filtered[KEY_COLUMN] == key_value].iloc[0]
            
            st.divider()
            st.markdown("### 🔎 Détails")
            detail_cols = st.columns(4)
            col_index = 0
            
            for col_name in view_cols:
                value = selected_row_data.get(col_name, "N/A")
                if col_name.startswith('Commentaire_'):
                    detail_cols[col_index % 4].markdown(f"**{col_name} :** {value if value else '-'}")
                else:
                    detail_cols[col_index % 4].metric(col_name, value if value else "-")
                col_index += 1
            st.divider()
        except Exception:
             pass

# --- ÉTAPES ---

def step_1_reception(df_data, column_headers):
    st.header("1️⃣ Import / Saisie Réception")
    
    with st.expander("📥 Import de Nouvelles Réceptions (Fichier Excel)", expanded=True):
        st.caption(f"Fichier Excel avec au moins : {', '.join(IMPORT_REQUIRED_COLUMNS)}.")
        uploaded_file = st.file_uploader(
            "Sélectionner un fichier", 
            type=['xlsx'],
            key=f"file_uploader_{st.session_state.uploader_key}" 
        )
        if uploaded_file is not None and st.button("🚀 Lancer l'Importation"):
            upload_new_receptions(uploaded_file, column_headers)
    
    st.markdown("---")
    st.subheader("Visualisation des Réceptions (Lecture Seule)")
    
    magasins = ['Tous'] + sorted(df_data['Magasin'].unique().tolist())
    sel_mag = st.selectbox("Magasin:", magasins, key="s1_mag")
    
    df_show = df_data.copy()
    if sel_mag != 'Tous':
        df_show = df_show[df_show['Magasin'] == sel_mag]
        
    display_data_editor(df_show, STEP_1_VIEW_COLUMNS, [])


def step_2_transport(df_data):
    st.header("2️⃣ Saisie Info Transport")
    
    # 4 colonnes de filtres
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        magasins = ['Tous'] + sorted(df_data['Magasin'].unique().tolist())
        sel_mag = st.selectbox("Magasin:", magasins, key="s2_mag")
    with c2:
        statuts = ['Tous'] + sorted(df_data['StatutLivraison'].unique().tolist())
        sel_stat = st.selectbox("Statut:", statuts, key="s2_stat")
    with c3:
        fournisseurs = ['Tous'] + sorted(df_data['Fournisseur'].unique().tolist())
        sel_fourn = st.selectbox("Fournisseur:", fournisseurs, key="s2_fourn")
    with c4:
        dates = ['Tous'] + sorted(df_data['Livré le'].astype(str).unique().tolist())
        sel_date = st.selectbox("Date (Livré le):", dates, key="s2_date")
    
    df_filtered = df_data.copy()
    if sel_mag != 'Tous': df_filtered = df_filtered[df_filtered['Magasin'] == sel_mag]
    if sel_stat != 'Tous': df_filtered = df_filtered[df_filtered['StatutLivraison'].astype(str).str.strip() == sel_stat.strip()]
    if sel_fourn != 'Tous': df_filtered = df_filtered[df_filtered['Fournisseur'] == sel_fourn]
    if sel_date != 'Tous': df_filtered = df_filtered[df_filtered['Livré le'].astype(str) == sel_date]

    c_head, c_btn = st.columns([3, 1])
    with c_head:
        st.subheader(f"Commandes : {len(df_filtered)}")
    with c_btn:
        if st.button("💾 Enregistrer", key="btn_save_s2"):
            save_data_to_gsheet(None, st.session_state['df_filtered_pre_edit'], st.session_state['column_headers'])
    
    edited_df = display_data_editor(df_filtered, STEP_2_VIEW_COLUMNS, STEP_2_EDITABLE)
    display_details(df_filtered, STEP_2_VIEW_COLUMNS)


def step_3_deballage(df_data):
    st.header("3️⃣ Saisie Déballage")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        magasins = ['Tous'] + sorted(df_data['Magasin'].unique().tolist())
        sel_mag = st.selectbox("Magasin:", magasins, key="s3_mag")
    with c2:
        litiges = ['Tous'] + sorted(df_data['LitigesDeballe'].unique().tolist()) if 'LitigesDeballe' in df_data.columns else ['Tous']
        sel_lit = st.selectbox("Litiges:", litiges, key="s3_lit")
    with c3:
        fournisseurs = ['Tous'] + sorted(df_data['Fournisseur'].unique().tolist())
        sel_fourn = st.selectbox("Fournisseur:", fournisseurs, key="s3_fourn")
    with c4:
        dates = ['Tous'] + sorted(df_data['Livré le'].astype(str).unique().tolist())
        sel_date = st.selectbox("Date (Livré le):", dates, key="s3_date")

    df_filtered = df_data.copy()
    if sel_mag != 'Tous': df_filtered = df_filtered[df_filtered['Magasin'] == sel_mag]
    if sel_lit != 'Tous': df_filtered = df_filtered[df_filtered['LitigesDeballe'].astype(str).str.strip() == sel_lit.strip()]
    if sel_fourn != 'Tous': df_filtered = df_filtered[df_filtered['Fournisseur'] == sel_fourn]
    if sel_date != 'Tous': df_filtered = df_filtered[df_filtered['Livré le'].astype(str) == sel_date]

    c_head, c_btn = st.columns([3, 1])
    with c_head:
        st.subheader(f"Commandes : {len(df_filtered)}")
    with c_btn:
        if st.button("💾 Enregistrer", key="btn_save_s3"):
            save_data_to_gsheet(edited_df, st.session_state['df_filtered_pre_edit'], st.session_state['column_headers'])
    
    edited_df = display_data_editor(df_filtered, STEP_3_VIEW_COLUMNS, STEP_3_EDITABLE)
    display_details(df_filtered, STEP_3_VIEW_COLUMNS)

def step_4_non_saisie():
    st.header("4️⃣ Marchandise non saisie")
    st.caption("Suivi quotidien des BLs physiques non saisis.")

    df_pending = load_non_saisie_data()
    
    with st.expander("➕ Ajouter une BL en attente", expanded=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            fourn = st.text_input("Fournisseur", key="p_fourn")
            bl = st.text_input("Numéro BL", key="p_bl")
        with c2:
            st.markdown("<br><br>", unsafe_allow_html=True)
            if st.button("Ajouter", disabled=not (fourn and bl)):
                add_pending_bl(fourn, bl)

    st.markdown("---")
    st.subheader(f"En attente : {len(df_pending)}")
    
    if df_pending.empty:
        st.info("Liste vide.")
        return

    edited_pending_df = st.data_editor(
        df_pending, 
        key="pending_bl_editor",
        use_container_width=True,
        hide_index=False,
        num_rows="dynamic", 
        column_order=PENDING_BL_COLUMNS,
        column_config={
            'Fournisseur': st.column_config.TextColumn('Fournisseur', disabled=True),
            'NuméroBL': st.column_config.TextColumn('Numéro BL', disabled=True),
            'DateReceptionPhysique': st.column_config.DatetimeColumn('Date Réception', format="YYYY-MM-DD", disabled=True), 
            'Statut': st.column_config.TextColumn('Statut', disabled=True)
        }
    )
    
    deleted_rows = st.session_state["pending_bl_editor"].get("deleted_rows", [])
    if deleted_rows:
        if st.button(f"🗑️ Confirmer suppression ({len(deleted_rows)})"):
            save_pending_bl_updates(df_pending, deleted_rows)

def step5_pdc_saisie(column_headers):
    st.header("5️⃣ Saisie Manuelle PDC")
    st.caption("Suivi des PDC (Feuille 'PDC').")

    df_pdc = load_pdc_data()

    # Formulaire d'ajout
    with st.expander("➕ Ajouter un PDC", expanded=True):
        with st.form("pdc_form"):
            c1, c2 = st.columns(2)
            with c1:
                fournisseur = st.text_input("Fournisseur")
                numero_bl = st.text_input("Numéro BL")
                date_reception = st.date_input("Date Réception Physique", datetime.now())
                acheteur = st.text_input("Acheteur")
            with c2:
                mail_acheteur = st.text_input("Mail Acheteur")
                date_relance = st.date_input("Date Relance", None)
                nb_relance = st.number_input("Nombre de relance", min_value=0, step=1)
            
            if st.form_submit_button("Ajouter PDC"):
                add_pdc_entry(fournisseur, numero_bl, date_reception, acheteur, mail_acheteur, date_relance, nb_relance)

    st.markdown("---")
    st.subheader(f"PDC en cours : {len(df_pdc)}")

    if df_pdc.empty:
        st.info("Aucun PDC.")
        return

    # Tableau avec suppression activée
    edited_pdc_df = st.data_editor(
        df_pdc,
        key="pdc_editor",
        use_container_width=True,
        hide_index=False,
        num_rows="dynamic",
        column_order=PDC_COLUMNS,
        column_config={
            'Fournisseur': st.column_config.TextColumn('Fournisseur', disabled=True),
            'NuméroBL': st.column_config.TextColumn('Numéro BL', disabled=True),
            'DateReceptionPhysique': st.column_config.DatetimeColumn('Date Réception', format="YYYY-MM-DD", disabled=True),
            'Acheteur': st.column_config.TextColumn('Acheteur', disabled=True),
            'mail acheteur': st.column_config.TextColumn('Mail Acheteur', disabled=True),
            'date relance': st.column_config.DatetimeColumn('Date Relance', format="YYYY-MM-DD", disabled=True),
            'Nombre de relance': st.column_config.NumberColumn('Nb Relance', disabled=True)
        }
    )

    deleted_rows = st.session_state["pdc_editor"].get("deleted_rows", [])
    if deleted_rows:
        if st.button(f"🗑️ Confirmer suppression ({len(deleted_rows)})"):
            save_pdc_updates(df_pdc, deleted_rows)


# --- MAIN ---
def main():
    st.set_page_config(page_title="Suivi Commandes", layout="wide", initial_sidebar_state="collapsed")

    if 'current_step' not in st.session_state: st.session_state.current_step = 'home'
    if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

    df_data, column_headers = load_data_from_gsheet()
    st.session_state['column_headers'] = column_headers
    
    with st.sidebar:
        st.title("Menu")
        if st.button("🏠 Accueil"): st.session_state.current_step = 'home'
        if st.button("1️⃣ Import / Vue"): st.session_state.current_step = 'step1'
        if st.button("2️⃣ Transport"): st.session_state.current_step = 'step2'
        if st.button("3️⃣ Déballage"): st.session_state.current_step = 'step3'
        if st.button("4️⃣ BLs en attente"): st.session_state.current_step = 'step4'
        if st.button("5️⃣ Saisie PDC"): st.session_state.current_step = 'step5'
        
        st.markdown("---")
        if st.button("🔄 Rafraîchir"):
            st.cache_data.clear()
            get_all_existing_ids.clear()
            load_non_saisie_data.clear()
            load_pdc_data.clear()
            st.rerun()

    if df_data.empty and st.session_state.current_step not in ['home', 'step1', 'step4', 'step5']:
        st.error("Aucune donnée chargée.")
        st.session_state.current_step = 'home'

    if st.session_state.current_step == 'home':
        st.title("📦 Suivi des Commandes")
        c1, c2, c3 = st.columns(3)
        with c1: 
            if st.button("1️⃣ Import / Vue", use_container_width=True): 
                st.session_state.current_step = 'step1'
                st.rerun()
        with c2: 
            if st.button("2️⃣ Transport", use_container_width=True): 
                st.session_state.current_step = 'step2'
                st.rerun()
        with c3: 
            if st.button("3️⃣ Déballage", use_container_width=True): 
                st.session_state.current_step = 'step3'
                st.rerun()
        st.markdown("---")
        c4, c5 = st.columns(2)
        with c4:
            if st.button("4️⃣ BLs en attente", use_container_width=True):
                st.session_state.current_step = 'step4'
                st.rerun()
        with c5:
            if st.button("5️⃣ Saisie PDC", use_container_width=True):
                st.session_state.current_step = 'step5'
                st.rerun()

    elif st.session_state.current_step == 'step1': step_1_reception(df_data, column_headers)
    elif st.session_state.current_step == 'step2': step_2_transport(df_data)
    elif st.session_state.current_step == 'step3': step_3_deballage(df_data)
    elif st.session_state.current_step == 'step4': step_4_non_saisie()
    elif st.session_state.current_step == 'step5': step5_pdc_saisie(column_headers)

if __name__ == '__main__':
    main()
