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

# --- DÉFINITION DES COLONNES PAR ÉTAPE ---

# Colonnes de l'Excel (Lecture seule, utilisées dans toutes les étapes)
ESSENTIAL_EXCEL_COLUMNS = ['Magasin', 'Fournisseur', 'Mt HT'] 
KEY_COLUMN = 'NuméroAuto'

# Colonnes pour les BLs en attente de saisie informatique (Étape 4)
PENDING_BL_COLUMNS = ['Fournisseur', 'NuméroBL', 'DateReceptionPhysique', 'Statut']

# Étape 1: Import ou Saisie Réception (Colonnes pour l'affichage de cette étape)
STEP_1_COLUMNS = ESSENTIAL_EXCEL_COLUMNS + ['PDC', 'AcheteurPDC']

# Étape 2: Saisie Info Transport (Mise à jour avec les colonnes demandées)
STEP_2_EDIT_COLUMNS = [
    'StatutLivraison', 'NomTransporteur', 'NomSaisie', 
    'DateLivraison', 'HeureLivraison', 'Emplacement', 'NbPalettes', 
    'Poids_total', 'Commentaire_Livraison'
]

# Étape 3: Saisie Déballage (Mise à jour avec les colonnes demandées)
STEP_3_EDIT_COLUMNS = [
    'Colis_manquant/abimé/ouvert', 'NomDeballage', 'DateDebutDeballage', 
    'Litiges', 'Commentaire_litige'
]

# Toutes les colonnes manuelles (pour la fonction de sauvegarde)
APP_MANUAL_COLUMNS = STEP_2_EDIT_COLUMNS + STEP_3_EDIT_COLUMNS

# Toutes les colonnes finales de la vue Application
APP_VIEW_COLUMNS = [KEY_COLUMN] + ESSENTIAL_EXCEL_COLUMNS + ['PDC', 'AcheteurPDC'] + APP_MANUAL_COLUMNS

# Colonnes requises pour le fichier d'importation de nouvelles réceptions (minimum)
IMPORT_REQUIRED_COLUMNS = [KEY_COLUMN, 'Magasin', 'Fournisseur', 'Mt HT'] 

# Liste de toutes les colonnes de la feuille (y compris Clôturé)
SHEET_REQUIRED_COLUMNS = APP_VIEW_COLUMNS + ['Clôturé']


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
        # ... (autres clés de l'authentification)
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": creds_for_auth.get('client_x509_cert_url', '')
    }
    
    return gspread.service_account_from_dict(json_key_content)

@st.cache_data(ttl=600) 
def load_data_from_gsheet():
    """ 
    Lit la Google Sheet 'DATA' et retourne un DataFrame avec les commandes ouvertes
    ainsi que les en-têtes de colonnes.
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
        
        # Validation des colonnes essentielles
        required_cols = [KEY_COLUMN, 'Clôturé'] + ESSENTIAL_EXCEL_COLUMNS
        for col in required_cols:
            if col not in df_full.columns:
                 st.error(f"Colonne essentielle '{col}' manquante dans la Google Sheet.")
                 return pd.DataFrame(), []
        
        # Typage de base
        df_full[KEY_COLUMN] = df_full[KEY_COLUMN].astype(str).str.strip()
        df_full['Clôturé'] = df_full['Clôturé'].astype(str).str.strip().str.upper()

        # Garantir que toutes les colonnes manuelles sont de type string et initialisées à vide si manquantes
        for col in APP_MANUAL_COLUMNS + ['PDC', 'AcheteurPDC']:
            if col in df_full.columns:
                df_full[col] = df_full[col].fillna('').astype(str).str.strip()
            # Si la colonne n'existe pas dans le DF, le reindexage plus tard la créera
            
        # Filtrage des commandes NON Clôturées
        df_open = df_full[df_full['Clôturé'] != 'OUI'].copy()
        
        # S'assurer que le DF pour l'App a toutes les colonnes définies dans APP_VIEW_COLUMNS (pour la robustesse)
        df_app_view = df_open.reindex(columns=APP_VIEW_COLUMNS)
        
        # Ré-initialiser les NaNs aux chaînes vides pour l'affichage/édition Streamlit
        df_app_view[APP_VIEW_COLUMNS] = df_app_view[APP_VIEW_COLUMNS].fillna('')
        
        df_app_view = df_app_view.sort_values(by=KEY_COLUMN, ascending=True).reset_index(drop=True)
        
        st.success(f"Données chargées : {len(df_app_view)} commandes ouvertes prêtes.")
        return df_app_view, column_headers

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
            # Trouver l'index de la colonne clé
            key_col_index = column_headers.index(KEY_COLUMN) + 1 
        except ValueError:
            st.error(f"Colonne essentielle '{KEY_COLUMN}' introuvable dans la Google Sheet pour la vérification des IDs.")
            return set()

        # Récupérer toutes les valeurs de cette colonne (sauter la ligne d'en-tête)
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
            
            # Récupération de la clé (NuméroAuto) du DF filtré *avant* édition
            key_value = df_filtered_pre_edit.iloc[filtered_index][KEY_COLUMN]
            
            # Recherche de la ligne physique dans Google Sheet
            cell = worksheet.find(str(key_value), in_column=key_col_index)
            
            if cell is None:
                st.error(f"Clé '{key_value}' introuvable. Ligne non sauvegardée.")
                continue
                
            physical_row = cell.row
            
            for col_name, new_value in changes.items():
                
                col_index = col_to_index.get(col_name)
                
                if col_index is None:
                    st.warning(f"La colonne '{col_name}' est introuvable dans la Google Sheet. Ignorée.")
                    continue
                    
                updates.append({
                    'range': gspread.utils.rowcol_to_a1(physical_row, col_index),
                    'values': [[str(new_value)]] 
                })

        if updates:
            worksheet.batch_update(updates)
            st.success(f"💾 {len(edited_rows)} ligne(s) mise(s) à jour avec succès!")
            
            # Nettoyage et relance
            st.cache_data.clear()
            get_all_existing_ids.clear() # Vider le cache des IDs
            st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde des données : {e}")

def upload_new_receptions(uploaded_file, column_headers):
    """
    Lit un fichier Excel et ajoute les nouvelles réceptions à la Google Sheet,
    en vérifiant qu'il n'y ait pas de doublons sur le NuméroAuto.
    """
    if uploaded_file is None: return

    try:
        df_new = pd.read_excel(uploaded_file, engine='openpyxl')
        df_new.columns = df_new.columns.str.strip()
        
        missing_cols = [col for col in IMPORT_REQUIRED_COLUMNS if col not in df_new.columns]
        if missing_cols:
            st.error(f"Fichier Excel incomplet. Colonnes manquantes : {', '.join(missing_cols)}")
            return
            
        # --- NOUVEAU CONTRÔLE DE DOUBLONS ---
        df_new[KEY_COLUMN] = df_new[KEY_COLUMN].astype(str).str.strip()
        
        # 1. Doublons INTERNES au fichier d'import
        internal_duplicates = df_new[df_new.duplicated(subset=[KEY_COLUMN], keep=False)][KEY_COLUMN].unique()
        if len(internal_duplicates) > 0:
            st.warning(f"⚠️ {len(internal_duplicates)} NuméroAuto en doublon dans le fichier d'importation. Les doublons seront ignorés.")
        
        # Filtrer les doublons internes pour obtenir les IDs uniques à vérifier
        df_unique_to_check = df_new.drop_duplicates(subset=[KEY_COLUMN], keep='first')
        
        # 2. Doublons EXTERNES (vs Google Sheet)
        existing_ids = get_all_existing_ids(column_headers)
        external_duplicates = df_unique_to_check[df_unique_to_check[KEY_COLUMN].isin(existing_ids)][KEY_COLUMN].tolist()
        
        if len(external_duplicates) > 0:
            st.error(f"❌ {len(external_duplicates)} NuméroAuto sont déjà présents dans la base de données et seront ignorés.")
            st.caption(f"Doublons : {', '.join(external_duplicates[:5])}{'...' if len(external_duplicates) > 5 else ''}")
        
        # 3. Filtrage final : ne garder que les lignes uniques et non existantes
        df_to_append = df_unique_to_check[~df_unique_to_check[KEY_COLUMN].isin(existing_ids)].copy()
        
        if df_to_append.empty:
            st.warning("Aucune nouvelle ligne unique à importer après vérification des doublons.")
            return

        # --- FIN CONTRÔLE DE DOUBLONS ---
            
        df_insert = df_to_append.copy()
        
        # Initialisation des colonnes manquantes
        for col in column_headers:
            if col not in df_insert.columns:
                if col == 'Clôturé':
                    df_insert[col] = 'NON' 
                elif col == 'PDC':
                    df_insert[col] = 'NON' # Par défaut, NON PDC à l'import
                else:
                    df_insert[col] = ''
        
        # S'assurer que l'ordre des colonnes correspond aux en-têtes de la feuille
        df_insert = df_insert.reindex(columns=column_headers)
        df_insert = df_insert.fillna('').astype(str)
        data_to_append = df_insert.values.tolist()
        
        if not data_to_append:
            st.warning("Le fichier Excel ne contient aucune donnée à importer après filtration.")
            return

        # Insertion dans Google Sheet
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        worksheet.append_rows(data_to_append, value_input_option='USER_ENTERED')
        
        st.success(f"✅ **{len(data_to_append)}** nouvelle(s) réception(s) importée(s) avec succès!")
        
        # Réinitialisation de l'uploader et relance
        st.session_state.uploader_key += 1 
        st.cache_data.clear()
        get_all_existing_ids.clear() # Vider le cache des IDs
        st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de l'importation : {e}")


def add_new_pdc_reception(magasin, fournisseur, mt_ht, acheteur_pdc, date_livraison, column_headers):
    """ Ajoute manuellement une nouvelle commande PDC à la feuille. """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)

        # 1. Générer le NuméroAuto (utilise le timestamp pour garantir l'unicité)
        num_auto = f"PDC-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 2. Créer la nouvelle ligne de données
        new_row_data = {col: '' for col in column_headers} # Initialiser toutes les colonnes à vide
        
        # Remplir les champs spécifiques
        new_row_data[KEY_COLUMN] = num_auto
        new_row_data['Magasin'] = magasin
        new_row_data['Fournisseur'] = fournisseur
        new_row_data['Mt HT'] = str(mt_ht)
        new_row_data['AcheteurPDC'] = acheteur_pdc
        new_row_data['DateLivraison'] = date_livraison.strftime('%Y-%m-%d') # Format date pour la livraison
        new_row_data['PDC'] = 'OUI' # Marquer comme PDC
        new_row_data['Clôturé'] = 'NON' # Nouvelle commande

        # 3. Préparer pour l'insertion (Liste de valeurs dans l'ordre des en-têtes)
        data_to_append = [[new_row_data.get(col, '') for col in column_headers]]
        
        # 4. Insertion dans Google Sheet
        worksheet.append_rows(data_to_append, value_input_option='USER_ENTERED')
        
        st.success(f"✅ Commande PDC '{num_auto}' ajoutée avec succès!")
        st.cache_data.clear()
        get_all_existing_ids.clear() # Vider le cache des IDs
        st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de la saisie manuelle : {e}")


# --- FONCTIONS POUR L'Étape 4 : Marchandise Non Saisie ---

@st.cache_data(ttl=60)
def load_non_saisie_data():
    """ 
    Lit la feuille Google pour les BLs en attente de saisie informatique 
    et s'assure que la colonne de date est de type datetime.
    """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        
        # Tente de trouver ou de créer la feuille si elle n'existe pas
        try:
            worksheet = sh.worksheet(PENDING_BL_WORKSHEET_NAME)
        except gspread.WorksheetNotFound:
            # Si la feuille n'existe pas, la créer avec les en-têtes
            st.warning(f"La feuille '{PENDING_BL_WORKSHEET_NAME}' n'existe pas. Création...")
            worksheet = sh.add_worksheet(title=PENDING_BL_WORKSHEET_NAME, rows=1, cols=len(PENDING_BL_COLUMNS))
            worksheet.append_row(PENDING_BL_COLUMNS)
            st.info(f"Feuille '{PENDING_BL_WORKSHEET_NAME}' créée avec succès.")
            return pd.DataFrame(columns=PENDING_BL_COLUMNS)

        with st.spinner(f'Chargement des BLs en attente...'):
            df = pd.DataFrame(worksheet.get_all_records())
        
        # S'assurer que les colonnes nécessaires existent
        df = df.reindex(columns=PENDING_BL_COLUMNS)
        
        # FIX pour la StreamlitAPIException: Assurer que la colonne de date est de type datetime
        if 'DateReceptionPhysique' in df.columns:
            # Convertir la colonne en datetime. 'errors=coerce' tourne les dates invalides en NaT.
            df['DateReceptionPhysique'] = pd.to_datetime(df['DateReceptionPhysique'], errors='coerce')
            
            # Trier le DF en utilisant la colonne datetime
            df = df.sort_values(by='DateReceptionPhysique', ascending=False)
            
        # S'assurer que les autres colonnes sont des chaînes (pour la robustesse)
        for col in PENDING_BL_COLUMNS:
            if col != 'DateReceptionPhysique' and col in df.columns:
                df[col] = df[col].fillna('').astype(str)

        # Le reindexage est déjà fait, NaT (non-valeur pour datetime) est correct.
        return df

    except Exception as e:
        st.error(f"Erreur de chargement des BLs en attente. Erreur: {e}")
        return pd.DataFrame(columns=PENDING_BL_COLUMNS)

def save_pending_bl_updates(df_current, deleted_rows):
    """
    Met à jour la feuille BL_EN_ATTENTE en supprimant les lignes cochées.
    """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(PENDING_BL_WORKSHEET_NAME)
        
        # Créer le DataFrame final à sauvegarder en retirant les lignes supprimées
        # deleted_rows contient les index du df_pending initial.
        df_final = df_current.drop(deleted_rows).reset_index(drop=True)

        # Convertir les colonnes datetime en chaînes de caractères (format YYYY-MM-DD)
        # pour l'écriture dans Google Sheets
        if 'DateReceptionPhysique' in df_final.columns:
             df_final['DateReceptionPhysique'] = df_final['DateReceptionPhysique'].dt.strftime('%Y-%m-%d').fillna('')

        # 1. Préparation des données pour l'écriture (y compris les en-têtes)
        data_to_save = [PENDING_BL_COLUMNS] + df_final.values.tolist()
        
        # 2. Écrasement complet de la feuille (plus simple et plus sûr pour cette petite liste)
        worksheet.clear()
        worksheet.update('A1', data_to_save)
        
        st.success(f"🗑️ {len(deleted_rows)} BL(s) marqué(s) comme saisi(s) informatiquement et supprimé(s).")
        
        # Nettoyage et relance
        st.cache_data.clear()
        load_non_saisie_data.clear() # Vider le cache de cette fonction
        st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de la mise à jour des BLs en attente : {e}")

def add_pending_bl(fournisseur, numero_bl):
    """ Ajoute manuellement une nouvelle BL en attente. """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(PENDING_BL_WORKSHEET_NAME)

        # Construction de la ligne
        new_row = {
            'Fournisseur': fournisseur,
            'NuméroBL': numero_bl,
            'DateReceptionPhysique': datetime.now().strftime('%Y-%m-%d'), # Date au format string
            'Statut': 'à saisir'
        }
        
        # Préparation des données dans l'ordre des colonnes
        data_to_append = [[new_row.get(col, '') for col in PENDING_BL_COLUMNS]]
        
        # Insertion dans Google Sheet (utilise la première ligne vide)
        worksheet.append_rows(data_to_append, value_input_option='USER_ENTERED')
        
        st.success(f"✅ BL en attente '{numero_bl}' ajoutée pour le suivi.")
        load_non_saisie_data.clear() # Vider le cache
        st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de l'ajout de la BL en attente : {e}")


# --- 3. FONCTIONS D'AFFICHAGE DES ÉTAPES ---

def step_1_reception(df_data, column_headers):
    """ Étape 1 : Import de Nouvelles Réceptions. (Saisie Manuelle PDC déplacée vers l'étape 5)"""
    st.header("1️⃣ Import de Nouvelles Réceptions")
    st.caption("Cette étape sert à ajouter de nouvelles commandes via un fichier Excel.")
    
    # --- Importation ---
    with st.expander("📥 Import de Nouvelles Réceptions (Fichier Excel)", expanded=True):
        st.caption(f"Fichier requis : Excel (.xlsx) avec au moins les colonnes : {', '.join(IMPORT_REQUIRED_COLUMNS)}.")
        st.warning("⚠️ Attention : Un contrôle de doublons est effectué sur la colonne 'NuméroAuto'. Les doublons ne seront pas importés.")
        uploaded_file = st.file_uploader(
            "Sélectionner un fichier Excel", 
            type=['xlsx'],
            key=f"file_uploader_{st.session_state.uploader_key}" 
        )
        if uploaded_file is not None and st.button("🚀 Lancer l'Importation"):
            upload_new_receptions(uploaded_file, column_headers)


def display_data_editor(df_filtered, editable_cols):
    """ Fonction utilitaire pour configurer et afficher le st.data_editor. """
    
    # Configuration des colonnes: lecture seule pour les colonnes non éditables de l'étape
    column_configs = {
        col: st.column_config.Column(
            col,
            disabled=(col not in editable_cols)
        ) for col in APP_VIEW_COLUMNS
    }
    
    # La sauvegarde utilise df_filtered_pre_edit pour le mapping.
    st.session_state['df_filtered_pre_edit'] = df_filtered.copy()

    # Le data_editor doit utiliser le DF filtré
    edited_df = st.data_editor(
        df_filtered, 
        key="command_editor",
        height=500,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic", # IMPORTANT : Permet la sélection et la suppression de lignes
        column_order=[col for col in APP_VIEW_COLUMNS if col in df_filtered.columns],
        column_config=column_configs,
        # Clé incrémentée lors de la sauvegarde/import pour réinitialiser l'état d'édition
    )
    return edited_df

def step_2_transport(df_data):
    """ Étape 2 : Saisie Info Transport. """
    st.header("2️⃣ Saisie Informations Transport")
    
    # Affichage des filtres pour l'étape 2 (dans le corps principal)
    col_filters_1, col_filters_2 = st.columns(2)
    with col_filters_1:
        magasins = ['Tous'] + sorted(df_data['Magasin'].unique().tolist())
        selected_magasin = st.selectbox("Filtrer par Magasin:", magasins, key="filter_magasin_2")
    with col_filters_2:
        statuts = ['Tous'] + sorted(df_data['StatutLivraison'].unique().tolist())
        selected_statut = st.selectbox("Filtrer par Statut Livraison:", statuts, key="filter_statut_2")
    
    # Application des filtres
    df_filtered = df_data.copy()
    if selected_magasin != 'Tous':
        df_filtered = df_filtered[df_filtered['Magasin'] == selected_magasin]
    if selected_statut != 'Tous':
        df_filtered = df_filtered[df_filtered['StatutLivraison'].astype(str).str.strip() == selected_statut.strip()]

    st.subheader(f"Commandes à traiter : {len(df_filtered)} / {len(df_data)}")
    
    edited_df = display_data_editor(df_filtered, STEP_2_EDIT_COLUMNS)
    
    # Affichage des détails (réutilisé)
    display_details(df_filtered, STEP_2_EDIT_COLUMNS)

    # Bouton de Sauvegarde
    if st.button("💾 Enregistrer les modifications du Transport"):
        save_data_to_gsheet(edited_df, st.session_state['df_filtered_pre_edit'], st.session_state['column_headers'])


def step_3_deballage(df_data):
    """ Étape 3 : Saisie Déballage. """
    st.header("3️⃣ Saisie et Validation Déballage")

    # Affichage des filtres pour l'étape 3 (dans le corps principal)
    col_filters_1, col_filters_2 = st.columns(2)
    with col_filters_1:
        magasins = ['Tous'] + sorted(df_data['Magasin'].unique().tolist())
        selected_magasin = st.selectbox("Filtrer par Magasin:", magasins, key="filter_magasin_3")
    with col_filters_2:
        litiges = ['Tous'] + sorted(df_data['Litiges'].unique().tolist())
        selected_litige = st.selectbox("Filtrer par Litiges:", litiges, key="filter_litige_3")

    # Application des filtres
    df_filtered = df_data.copy()
    if selected_magasin != 'Tous':
        df_filtered = df_filtered[df_filtered['Magasin'] == selected_magasin]
    if selected_litige != 'Tous':
        df_filtered = df_filtered[df_filtered['Litiges'].astype(str).str.strip() == selected_litige.strip()]

    st.subheader(f"Commandes à valider : {len(df_filtered)} / {len(df_data)}")
    
    edited_df = display_data_editor(df_filtered, STEP_3_EDIT_COLUMNS)
    
    # Affichage des détails (réutilisé)
    display_details(df_filtered, STEP_3_EDIT_COLUMNS)

    # Bouton de Sauvegarde
    if st.button("💾 Enregistrer les modifications du Déballage"):
        save_data_to_gsheet(edited_df, st.session_state['df_filtered_pre_edit'], st.session_state['column_headers'])


def step_4_non_saisie():
    """ Étape 4 : Marchandise non saisie / BLs en attente de saisie informatique. """
    st.header("4️⃣ Marchandise non saisie (Suivi Quotidien des BLs)")
    st.caption("Utilisez cette étape pour lister les Bons de Livraison reçus physiquement, mais pas encore entrés dans le système de gestion des commandes (Feuille DATA).")

    df_pending = load_non_saisie_data()
    
    # --- Formulaire d'ajout rapide ---
    with st.expander("➕ Ajouter une nouvelle BL en attente", expanded=True):
        col_form_1, col_form_2 = st.columns([3, 1])
        with col_form_1:
            pending_fournisseur = st.text_input("Fournisseur", key="pending_fournisseur_input")
            pending_bl = st.text_input("Numéro du Bon de Livraison (BL)", key="pending_bl_input")
        with col_form_2:
            st.markdown("<br><br>", unsafe_allow_html=True) # Espace pour alignement
            if st.button("Ajouter à la liste de suivi", disabled=not (pending_fournisseur and pending_bl)):
                add_pending_bl(pending_fournisseur, pending_bl)

    st.markdown("---")
    
    st.subheader(f"BLs en attente de saisie informatique : {len(df_pending)}")
    
    # --- Affichage et suppression ---
    if df_pending.empty:
        st.info("La liste de suivi est vide. Toutes les BLs physiques ont été saisies.")
        return

    # Utiliser st.data_editor pour permettre la sélection/suppression visuelle
    edited_pending_df = st.data_editor(
        df_pending, 
        key="pending_bl_editor",
        use_container_width=True,
        hide_index=False,
        num_rows="dynamic", 
        column_order=PENDING_BL_COLUMNS,
        column_config={
            # Ces colonnes doivent être de type string dans le DF, ce qui est assuré
            'Fournisseur': st.column_config.TextColumn('Fournisseur', disabled=True),
            'NuméroBL': st.column_config.TextColumn('Numéro BL', disabled=True),
            # La colonne est bien de type datetime64 dans le DF grâce au FIX
            'DateReceptionPhysique': st.column_config.DatetimeColumn('Date Réception Physique', format="YYYY-MM-DD", disabled=True), 
            'Statut': st.column_config.TextColumn('Statut', disabled=True)
        }
    )
    
    # Bouton de confirmation de suppression (après saisie informatique)
    # On récupère les index des lignes que l'utilisateur a supprimées via l'icône poubelle native
    deleted_rows_indices = st.session_state["pending_bl_editor"].get("deleted_rows", [])

    if deleted_rows_indices:
        st.warning(f"Vous avez marqué {len(deleted_rows_indices)} BL(s) comme **saisi(s)** dans le système.")
        if st.button(f"🗑️ Confirmer la suppression de {len(deleted_rows_indices)} BL(s)"):
            # L'index renvoyé par deleted_rows est l'index dans le DF original (df_pending)
            save_pending_bl_updates(df_pending, deleted_rows_indices)
    else:
        st.info("Sélectionnez la ou les lignes que vous avez saisies dans le système, puis cliquez sur l'icône poubelle (🗑️) pour les supprimer du suivi.")


def step5_pdc_saisie(column_headers):
    """ Nouvelle Étape 5 : Saisie Manuelle PDC (Commande Ponctuelle). """
    st.header("5️⃣ Saisie Manuelle PDC (Commande Ponctuelle)")
    st.caption("Ajoutez ici les commandes PDC qui ne passent pas par l'import de masse.")

    with st.expander("➕ Formulaire de Saisie PDC", expanded=True):
        with st.form("pdc_form"):
            col_form_1, col_form_2, col_form_3 = st.columns(3)
            with col_form_1:
                magasin = st.text_input("Magasin (Code)", max_chars=10)
                fournisseur = st.text_input("Fournisseur", max_chars=50)
            with col_form_2:
                mt_ht = st.number_input("Montant HT (€)", min_value=0.0, step=0.01, format="%.2f")
                acheteur_pdc = st.text_input("Acheteur PDC", max_chars=50)
            with col_form_3:
                date_livraison = st.date_input("Date de Livraison Estimée", datetime.now())
                
            submitted = st.form_submit_button("Valider la Saisie PDC", disabled=not (magasin and fournisseur and acheteur_pdc))
            
            if submitted:
                add_new_pdc_reception(magasin, fournisseur, mt_ht, acheteur_pdc, date_livraison, column_headers)


def display_details(df_filtered, editable_cols):
    """ Fonction utilitaire pour afficher les détails de la ligne sélectionnée. """
    selection_state = st.session_state.get("command_editor", {}).get("selection", {})
    selected_rows_indices = selection_state.get("rows", [])
    
    if selected_rows_indices and not df_filtered.empty:
        selected_index = selected_rows_indices[0]
        
        try:
            selected_row_data = df_filtered.iloc[selected_index] 
            
            st.divider()
            st.markdown("### 🔎 Détails de la Commande Sélectionnée")
            
            # Affichage des colonnes clés, puis des colonnes éditables
            details_to_show = [KEY_COLUMN, 'Magasin', 'Fournisseur'] + editable_cols
            
            detail_cols = st.columns(4)
            col_index = 0
            
            for col_name in details_to_show:
                if col_name in selected_row_data.index:
                    value = selected_row_data[col_name]
                else:
                    value = "N/A" # Au cas où une colonne est manquante
                
                if col_name.startswith('Commentaire_'):
                    detail_cols[col_index % 4].markdown(f"**{col_name} :** {value if value else 'Non spécifié'}")
                else:
                    detail_cols[col_index % 4].metric(col_name, value if value else "Non spécifié")
                col_index += 1
            st.divider()

        except Exception:
             # Gère les erreurs d'index ou de relance silencieusement
             pass


# --- 4. LOGIQUE ET AFFICHAGE STREAMLIT PRINCIPAL ---

def main():
    st.set_page_config(
        page_title="Suivi des Commandes Multi-Étapes",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # --- Initialisation de l'état de la session ---
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 'home'
    if 'uploader_key' not in st.session_state:
        st.session_state.uploader_key = 0

    # 1. Chargement des données (avec mise en cache)
    df_data, column_headers = load_data_from_gsheet()
    
    st.session_state['column_headers'] = column_headers
    
    # --- Barre de Navigation Latérale ---
    with st.sidebar:
        st.title("Navigation App")
        if st.button("🏠 Accueil", key="nav_home"):
            st.session_state.current_step = 'home'
        if st.button("1️⃣ Import Réception", key="nav_step1"):
            st.session_state.current_step = 'step1'
        if st.button("2️⃣ Saisie Info Transport", key="nav_step2"):
            st.session_state.current_step = 'step2'
        if st.button("3️⃣ Saisie Déballage", key="nav_step3"):
            st.session_state.current_step = 'step3'
        if st.button("4️⃣ Marchandise non saisie (BLs)", key="nav_step4"):
            st.session_state.current_step = 'step4'
        if st.button("5️⃣ Saisie Manuelle PDC", key="nav_step5"): # NOUVEAU
            st.session_state.current_step = 'step5'
        
        st.markdown("---")
        if st.button("🔄 Rafraîchir les données", key="refresh_data_side"):
            st.cache_data.clear()
            get_all_existing_ids.clear() # Vider le cache des IDs
            load_non_saisie_data.clear() # Vider le cache des BLs en attente
            st.rerun() 
            
    # Si les données ne sont pas chargées, afficher un message et empêcher la navigation
    if df_data.empty and st.session_state.current_step not in ['home', 'step1', 'step4', 'step5']:
        st.error("Veuillez rafraîchir ou importer des données pour commencer.")
        st.session_state.current_step = 'home'


    # --- Affichage du contenu basé sur l'état de la session ---
    if st.session_state.current_step == 'home':
        st.title("📦 Application de Suivi des Commandes en Cours")
        st.subheader("Sélectionnez une étape pour commencer le traitement.")
        
        col_home1, col_home2, col_home3 = st.columns(3)
        
        with col_home1:
            if st.button("Étape 1: Import Réception", use_container_width=True, help="Ajouter de nouvelles commandes au suivi via fichier."):
                 st.session_state.current_step = 'step1'
                 st.rerun()
        with col_home2:
            if st.button("Étape 2: Saisie Info Transport", use_container_width=True, help="Mettre à jour les informations de logistique et de livraison."):
                 st.session_state.current_step = 'step2'
                 st.rerun()
        with col_home3:
            if st.button("Étape 3: Saisie Déballage", use_container_width=True, help="Valider le contrôle, le déballage et gérer les litiges."):
                 st.session_state.current_step = 'step3'
                 st.rerun()
        
        st.markdown("---")
        col_home4, col_home5 = st.columns(2)
        with col_home4:
            if st.button("Étape 4: Marchandise non saisie", use_container_width=True, help="Suivi quotidien des Bons de Livraison reçus physiquement."):
                st.session_state.current_step = 'step4'
                st.rerun()
        with col_home5:
            if st.button("Étape 5: Saisie Manuelle PDC", use_container_width=True, help="Ajouter une commande Ponctuelle (PDC) manuellement."):
                st.session_state.current_step = 'step5'
                st.rerun()
            
        st.info(f"Commandes Ouvertes Actuellement : **{len(df_data)}**")
        
    elif st.session_state.current_step == 'step1':
        step_1_reception(df_data, column_headers)
        
    elif st.session_state.current_step == 'step2':
        step_2_transport(df_data)
        
    elif st.session_state.current_step == 'step3':
        step_3_deballage(df_data)

    elif st.session_state.current_step == 'step4':
        step_4_non_saisie()
        
    elif st.session_state.current_step == 'step5':
        step5_pdc_saisie(column_headers)


if __name__ == '__main__':
    main()
