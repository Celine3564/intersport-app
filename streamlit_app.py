import pandas as pd
import gspread
import streamlit as st
import time

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

# --- 2. FONCTION DE LECTURE FILTRÉE DES DONNÉES ---

@st.cache_data(ttl=600) # Mise en cache des données pendant 10 minutes
def load_data_from_gsheet():
    """ 
    Lit la Google Sheet, filtre les commandes ouvertes et les colonnes de la vue application.
    """
    try:
        # --- CONNEXION SÉCURISÉE VIA STREAMLIT SECRETS ---
        secrets_immutable = st.secrets['gspread']
        creds = dict(secrets_immutable)

        # Nettoyage de la clé privée pour s'assurer qu'elle est au bon format str
        private_key_value = creds.get('private_key', 'CLE_MANQUANTE')
        if private_key_value == 'CLE_MANQUANTE':
            st.error("Erreur critique : La clé 'private_key' est absente de la section [gspread] des secrets.")
            return pd.DataFrame()
        
        # Conversion en str, suppression des espaces, et remplacement des '\n' littéraux
        private_key_value = str(private_key_value).strip()
        creds['private_key'] = private_key_value.replace('\\n', '\n')
        
        # Connexion à gspread
        gc = gspread.service_account_from_dict(creds)
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        # Lecture de toutes les données
        with st.spinner('Chargement des données de Google Sheets...'):
            df_full = pd.DataFrame(worksheet.get_all_records())

        # Nettoyage et typage des colonnes
        df_full.columns = df_full.columns.str.strip()
        if 'Clôturé' not in df_full.columns:
             st.error("Colonne 'Clôturé' manquante dans la Google Sheet.")
             return pd.DataFrame()
        
        df_full[KEY_COLUMN] = df_full[KEY_COLUMN].astype(str).str.strip()
        df_full['Clôturé'] = df_full['Clôturé'].astype(str).str.strip().str.upper()

        # Filtrage des commandes NON Clôturées
        df_open = df_full[df_full['Clôturé'] != 'OUI'].copy()
        
        # Filtrage des colonnes pour la vue App
        df_app_view = df_open.reindex(columns=APP_VIEW_COLUMNS)
        
        df_app_view = df_app_view.sort_values(by=KEY_COLUMN, ascending=True).reset_index(drop=True)
        
        st.success(f"Données chargées : {len(df_app_view)} commandes ouvertes prêtes.")
        return df_app_view

    except KeyError:
        st.error("Erreur de configuration : Le secret Streamlit `gspread` est manquant. Veuillez le configurer dans les paramètres de l'application.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur lors de la connexion/lecture de la Google Sheet. Vérifiez l'ID et les permissions du compte de service : {e}")
        return pd.DataFrame()

# --- 3. FONCTION DE SAUVEGARDE DES DONNÉES (À IMPLÉMENTER PLUS TARD) ---

def save_data_to_gsheet(df_to_save):
    """
    Sauvegarde les données éditées par l'utilisateur dans la Google Sheet.
    (Implémentation à venir lorsque la connexion sera stable)
    """
    st.info("Fonction de sauvegarde temporairement désactivée en attendant la résolution de la connexion.")
    # Le code de sauvegarde sera inséré ici.
    pass


# --- 4. LOGIQUE ET AFFICHAGE STREAMLIT ---

def main():
    st.set_page_config(
        page_title="Suivi des Commandes Ouvertes",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("📦 Suivi des Commandes en Cours")
    st.caption("Affiche les commandes NON Clôturées de la Google Sheet, prêtes pour la mise à jour manuelle.")

    # 1. Chargement des données (avec mise en cache)
    df_data = load_data_from_gsheet()

    if df_data.empty:
        st.info("Aucune donnée n'a été chargée. Veuillez vérifier la connexion ou l'existence de commandes ouvertes.")
        return

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
        
    # 4. Affichage des résultats
    st.subheader(f"Commandes Ouvertes Filtrées ({len(df_filtered)} / {len(df_data)})")

    # Éditeur de données
    edited_df = st.data_editor(
        df_filtered,
        key="command_editor",
        height=500,
        use_container_width=True,
        hide_index=True,
        column_order=APP_VIEW_COLUMNS
    )

    # 5. Bouton de Rafraîchissement des données (pour recharger sans attendre le TTL du cache)
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 Rafraîchir les données"):
            st.cache_data.clear()
            st.rerun() 
            
    with col2:
        # Bouton de sauvegarde (temporairement inactif)
        if st.button("💾 Enregistrer les modifications"):
            save_data_to_gsheet(edited_df)


if __name__ == '__main__':
    main()
