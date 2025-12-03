import pandas as pd
import gspread
import streamlit as st
import time
import io 

# --- 1. CONFIGURATION ET CONSTANTES ---

# --- CONSTANTES GSPREAD ---
# L'ID unique de votre feuille Google
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk' 
# Le nom exact de l'onglet/feuille à l'intérieur du document
WORKSHEET_NAME = 'DATA' 

# --- DEFINITION DES COLONNES ---

# Colonnes de l'Application (Données saisies manuellement par les utilisateurs)
APP_MANUAL_COLUMNS = [
    'StatutLivraison', 'NomTransporteur', 'NomSaisie', 
    'DateLivraison', 'HeureLivraison', 'Emplacement', 'NbPalettes', 
    'Poids_total', 'Commentaire_Livraison', 'Colis_manquant/abimé/ouvert', 
    'NomDeballage', 'DateDebutDeballage', 'PDC', 'AcheteurPDC', 
    'Litiges', 'Commentaire_litige'
]

# Colonnes de l'Excel que l'application a besoin de VOIR (lecture seule)
ESSENTIAL_EXCEL_COLUMNS = ['Magasin', 'Fournisseur', 'Mt HT'] 

# Toutes les colonnes finales de la vue Application
APP_VIEW_COLUMNS = ['NuméroAuto'] + ESSENTIAL_EXCEL_COLUMNS + APP_MANUAL_COLUMNS

KEY_COLUMN = 'NuméroAuto'
# Colonnes requises pour le fichier d'importation de nouvelles réceptions (minimum)
IMPORT_REQUIRED_COLUMNS = [KEY_COLUMN, 'Magasin', 'Fournisseur', 'Mt HT'] 
# Liste de toutes les colonnes de la feuille (y compris Clôturé)
SHEET_REQUIRED_COLUMNS = [col.strip() for col in APP_VIEW_COLUMNS + ['Clôturé']]


# --- 2. FONCTION D'AUTHENTIFICATION (réutilisée pour la lecture et l'écriture) ---
def authenticate_gsheet():
    """Authentifie et retourne l'objet gspread Client."""
    secrets_immutable = st.secrets['gspread']
    creds_for_auth = dict(secrets_immutable)
    
    # Champs requis pour l'authentification JWT
    REQUIRED_KEYS = ['private_key', 'client_email', 'project_id', 'type']
    for key in REQUIRED_KEYS:
        if key not in creds_for_auth or not creds_for_auth[key]:
            raise ValueError(f"Erreur de configuration : Le secret '{key}' est manquant ou vide.")

    # Nettoyage de la clé privée
    private_key_value = str(creds_for_auth['private_key']).strip()
    cleaned_private_key = private_key_value.replace('\\n', '\n')
    
    # Création du dictionnaire final pour l'authentification
    json_key_content = {
        "type": creds_for_auth['type'],
        "project_id": creds_for_auth['project_id'],
        "private_key_id": creds_for_auth.get('private_key_id', ''),
        "private_key": cleaned_private_key,
        "client_email": creds_for_auth['client_email'],
        "client_id": creds_for_auth.get('client_id', ''),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": creds_for_auth.get('client_x509_cert_url', '')
    }
    
    return gspread.service_account_from_dict(json_key_content)

# --- 3. FONCTION DE LECTURE FILTRÉE DES DONNÉES ---
@st.cache_data(ttl=600) # Mise en cache des données pendant 10 minutes
def load_data_from_gsheet():
    """ 
    Lit la Google Sheet, filtre les commandes ouvertes et les colonnes de la vue application.
    """
    try:
        gc = authenticate_gsheet()
        
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        # Lecture de toutes les données
        with st.spinner('Chargement des données de Google Sheets...'):
            # Utilisation de get_all_records pour le DataFrame
            df_full = pd.DataFrame(worksheet.get_all_records())
            # Utilisation de get_all_values pour les en-têtes (nécessaire pour la sauvegarde et l'import)
            sheet_values = worksheet.get_all_values()
            column_headers = sheet_values[0] if sheet_values else []

        # Nettoyage et typage des colonnes
        df_full.columns = df_full.columns.str.strip()
        
        # Vérification des colonnes essentielles
        required_cols = [KEY_COLUMN, 'Clôturé'] + ESSENTIAL_EXCEL_COLUMNS
        for col in required_cols:
            if col not in df_full.columns:
                 st.error(f"Colonne essentielle '{col}' manquante dans la Google Sheet.")
                 return pd.DataFrame(), []
        
        df_full[KEY_COLUMN] = df_full[KEY_COLUMN].astype(str).str.strip()
        df_full['Clôturé'] = df_full['Clôturé'].astype(str).str.strip().str.upper()

        # Filtrage des commandes NON Clôturées
        df_open = df_full[df_full['Clôturé'] != 'OUI'].copy()
        
        # Filtrage des colonnes pour la vue App
        df_app_view = df_open.reindex(columns=APP_VIEW_COLUMNS)
        
        df_app_view = df_app_view.sort_values(by=KEY_COLUMN, ascending=True).reset_index(drop=True)
        
        st.success(f"Données chargées : {len(df_app_view)} commandes ouvertes prêtes.")
        # Retourne le DataFrame et les en-têtes du sheet pour la sauvegarde
        return df_app_view, column_headers

    except ValueError as e:
        # Erreur spécifique de configuration
        st.error(f"Erreur de configuration : {e}")
        return pd.DataFrame(), []
    except KeyError:
        # Erreur si la section [gspread] manque
        st.error("Erreur de configuration : Le secret Streamlit `gspread` est manquant. Veuillez le configurer dans les paramètres de l'application.")
        return pd.DataFrame(), []
    except Exception as e:
        # Erreur finale de connexion/permission
        st.error(f"Erreur de connexion/lecture. Le problème est lié aux PERMISSIONS de la Google Sheet. Erreur: {e}")
        return pd.DataFrame(), []

# --- 4. FONCTION DE SAUVEGARDE DES DONNÉES EXISTANTES ---
def save_data_to_gsheet(edited_df, df_filtered_pre_edit, column_headers):
    """
    Sauvegarde les données éditées par l'utilisateur dans la Google Sheet.
    """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        # Récupération des changements de l'éditeur Streamlit
        edited_rows = st.session_state["command_editor"]["edited_rows"]
        
        if not edited_rows:
            st.warning("Aucune modification détectée dans le tableau.")
            return

        updates = []
        
        # 1. Créer un mappage Colonne -> Index (1-basé)
        col_to_index = {header.strip(): i + 1 for i, header in enumerate(column_headers)}
        
        # 2. Trouver l'index de la colonne clé dans la feuille (pour la recherche)
        key_col_index = col_to_index.get(KEY_COLUMN)
        if not key_col_index:
            st.error(f"Colonne clé '{KEY_COLUMN}' introuvable dans la feuille Google. Sauvegarde annulée.")
            return

        # 3. Traiter chaque ligne modifiée
        for filtered_index, changes in edited_rows.items():
            
            # Récupérer la valeur unique de la clé (NuméroAuto) dans le tableau pré-édité
            key_value = df_filtered_pre_edit.iloc[filtered_index][KEY_COLUMN]
            
            # 4. Trouver la ligne physique dans la Google Sheet
            # La recherche se fait uniquement dans la colonne KEY_COLUMN
            cell = worksheet.find(str(key_value), in_column=key_col_index)
            
            if cell is None:
                st.error(f"Clé '{key_value}' introuvable dans la Google Sheet. Ligne non sauvegardée.")
                continue
                
            physical_row = cell.row
            
            # 5. Mettre à jour chaque colonne modifiée pour cette ligne
            for col_name, new_value in changes.items():
                
                # Récupérer l'index de la colonne physique
                col_index = col_to_index.get(col_name)
                
                if col_index is None:
                    st.warning(f"La colonne '{col_name}' est gérée par Streamlit mais introuvable dans la Google Sheet. Ignorée.")
                    continue
                    
                # Ajout de l'instruction de mise à jour à la liste
                updates.append({
                    'range': gspread.utils.rowcol_to_a1(physical_row, col_index),
                    'values': [[str(new_value)]] # Les valeurs doivent être dans un format [[value]]
                })

        # 6. Exécuter toutes les mises à jour en une seule fois (Batch Update)
        if updates:
            worksheet.batch_update(updates)
            st.success(f"💾 {len(edited_rows)} ligne(s) mise(s) à jour avec succès dans Google Sheet!")
            
            # 7. Nettoyer le cache et relancer l'application pour afficher les données actualisées
            st.cache_data.clear()
            st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde des données : {e}")

# --- 5. FONCTION D'IMPORTATION DE NOUVELLES RÉCEPTIONS ---
def upload_new_receptions(uploaded_file, column_headers):
    """
    Lit un fichier Excel et ajoute les nouvelles réceptions à la Google Sheet.
    """
    if uploaded_file is None:
        return

    try:
        # 1. Lecture du fichier Excel
        df_new = pd.read_excel(uploaded_file, engine='openpyxl')
        df_new.columns = df_new.columns.str.strip()
        
        # 2. Validation des colonnes
        missing_cols = [col for col in IMPORT_REQUIRED_COLUMNS if col not in df_new.columns]
        if missing_cols:
            st.error(f"Le fichier Excel doit contenir les colonnes suivantes : {', '.join(IMPORT_REQUIRED_COLUMNS)}. Colonnes manquantes : {', '.join(missing_cols)}")
            return
            
        # 3. Préparation des données pour l'insertion
        df_insert = df_new.copy()
        
        # S'assurer que les colonnes existent et sont initialisées
        for col in SHEET_REQUIRED_COLUMNS:
            if col not in df_insert.columns:
                if col == 'Clôturé':
                    df_insert[col] = 'NON' # Nouvelle commande = NON Clôturée
                else:
                    # Initialisation des colonnes manuelles à vide
                    df_insert[col] = '' 
        
        # S'assurer que l'ordre des colonnes correspond aux en-têtes de la feuille
        df_insert = df_insert.reindex(columns=column_headers)
        
        # Remplacer les NaN par des chaînes vides pour gspread
        df_insert = df_insert.fillna('').astype(str)
        
        # Conversion en liste de listes (lignes) pour l'insertion
        data_to_append = df_insert.values.tolist()
        
        if not data_to_append:
            st.warning("Le fichier Excel ne contient aucune donnée à importer.")
            return

        # 4. Insertion dans Google Sheet
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        # Utilisation de append_rows pour ajouter à la fin
        worksheet.append_rows(data_to_append, value_input_option='USER_ENTERED')
        
        st.success(f"✅ {len(data_to_append)} nouvelle(s) réception(s) importée(s) avec succès dans la Google Sheet!")
        
        # --- NOUVEAU : Vider l'uploader après l'importation réussie ---
        if 'uploader_key' in st.session_state:
            st.session_state.uploader_key += 1 # Incrémente la clé pour forcer la réinitialisation du composant
        
        # Nettoyer le cache et relancer pour afficher les nouvelles données
        st.cache_data.clear()
        st.rerun()

    except Exception as e:
        st.error(f"Erreur lors de l'importation du fichier Excel : {e}")
        st.info("Veuillez vérifier que le fichier est au format Excel (.xlsx) et que toutes les colonnes requises sont présentes.")


# --- 6. LOGIQUE ET AFFICHAGE STREAMLIT ---
def main():
    st.set_page_config(
        page_title="Suivi des Commandes Ouvertes",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("📦 Suivi des Commandes en Cours")
    st.caption("Affiche les commandes NON Clôturées de la Google Sheet, prêtes pour la mise à jour manuelle.")

    # Initialiser la clé de l'uploader pour permettre la réinitialisation après succès
    if 'uploader_key' not in st.session_state:
        st.session_state.uploader_key = 0

    # 1. Chargement des données (avec mise en cache)
    df_data, column_headers = load_data_from_gsheet()
    
    st.session_state['column_headers'] = column_headers

    if df_data.empty:
        st.info("Aucune donnée n'a été chargée. Veuillez vérifier la connexion ou l'existence de commandes ouvertes.")
    
    # --- SECTION IMPORTATION NOUVELLES RÉCEPTIONS (Feature 2) ---
    with st.sidebar.expander("Importer de Nouvelles Réceptions", expanded=False):
        st.caption("Fichier requis : Excel (.xlsx) avec au moins les colonnes 'NuméroAuto', 'Magasin', 'Fournisseur', 'Mt HT'.")
        uploaded_file = st.file_uploader(
            "Sélectionner un fichier Excel", 
            type=['xlsx'],
            key=f"file_uploader_{st.session_state.uploader_key}" # Utilise la clé pour la réinitialisation
        )
        if uploaded_file is not None and st.button("🚀 Importer les données"):
            upload_new_receptions(uploaded_file, column_headers)
            
    # 2. Sélecteurs et Barres de filtre (Sidebar)
    st.sidebar.header("Filtres")
    
    # Filtre sur la colonne Magasin
    magasins = ['Tous'] + sorted(df_data['Magasin'].unique().tolist())
    selected_magasin = st.sidebar.selectbox("Filtrer par Magasin:", magasins)

    # Filtre sur la colonne StatutLivraison
    statuts = ['Tous'] + sorted(df_data['StatutLivraison'].unique().tolist())
    selected_statut = st.sidebar.selectbox("Filtrer par Statut Livraison:", statuts)

    # 3. Application des filtres
    df_filtered = df_data.copy()

    if selected_magasin != 'Tous':
        df_filtered = df_filtered[df_filtered['Magasin'] == selected_magasin]

    if selected_statut != 'Tous':
        df_filtered = df_filtered[df_filtered['StatutLivraison'].astype(str).str.strip() == selected_statut.strip()]
        
    st.session_state['df_filtered_pre_edit'] = df_filtered.copy()

    # 4. Affichage des résultats
    st.subheader(f"Commandes Ouvertes Filtrées ({len(df_filtered)} / {len(df_data)})")

    # Configuration des colonnes (pour rendre les colonnes Excel non éditables)
    column_configs = {
        col: st.column_config.Column(
            col,
            disabled=(col not in APP_MANUAL_COLUMNS) # Désactive l'édition si ce n'est pas une colonne manuelle
        ) for col in APP_VIEW_COLUMNS
    }
    
    # Éditeur de données
    edited_df = st.data_editor(
        df_filtered,
        key="command_editor",
        height=500,
        use_container_width=True,
        hide_index=True,
        column_order=APP_VIEW_COLUMNS,
        column_config=column_configs,
        # Ajout de la sélection de ligne pour la fonctionnalité de détails
        on_select="rerun" # On relance l'app pour afficher les détails immédiatement
    )

    # 5. Affichage des détails de la ligne sélectionnée (Feature 1)
    if df_filtered.empty:
        # Ne pas essayer de lire la sélection si le DF est vide
        pass
    elif 'selection' in st.session_state["command_editor"] and st.session_state["command_editor"]["selection"]["rows"]:
        
        selected_index = st.session_state["command_editor"]["selection"]["rows"][0]
        
        # VÉRIFICATION DE SÉCURITÉ : Assure que l'index sélectionné est dans les limites du DataFrame actuel
        if selected_index < len(df_filtered):
            selected_row_data = df_filtered.iloc[selected_index]

            st.divider()
            st.markdown("### 🔎 Détails de la Commande Sélectionnée")
            
            # Utilisation de colonnes pour une meilleure mise en page
            detail_cols = st.columns(4)
            col_index = 0
            
            # Affichage des informations
            for col_name in APP_VIEW_COLUMNS:
                value = selected_row_data.get(col_name, "N/A")
                
                if col_name in ['Commentaire_Livraison', 'Commentaire_litige']:
                    # Utilisation de st.markdown pour les champs de commentaires longs
                    detail_cols[col_index % 4].markdown(f"**{col_name} :** {value if value else 'Non spécifié'}")
                else:
                    # Utilisation de st.metric pour les autres champs (plus compact)
                    detail_cols[col_index % 4].metric(col_name, value if value else "Non spécifié")
                col_index += 1
            st.divider()


    # 7. Bouton de Rafraîchissement et Sauvegarde
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 Rafraîchir les données"):
            st.cache_data.clear()
            st.rerun() 
            
    with col2:
        if st.button("💾 Enregistrer les modifications"):
            # Passer le DataFrame édité, la version d'avant édition pour le mapping, et les en-têtes
            save_data_to_gsheet(
                edited_df, 
                st.session_state['df_filtered_pre_edit'], 
                st.session_state['column_headers']
            )
            # Rerun est déjà dans save_data_to_gsheet

if __name__ == '__main__':
    main()
