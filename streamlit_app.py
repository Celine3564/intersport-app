import pandas as pd
import gspread
import streamlit as st
import time
import json # Importation nécessaire pour lire les secrets comme un JSON

# --- 1. CONFIGURATION ET CONSTANTES ---

# --- CONSTANTES GSPREAD (À METTRE À JOUR PAR VOS VALEURS) ---
# L'ID unique de votre feuille Google (longue chaîne de caractères dans l'URL)
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk' 
# Le nom exact de l'onglet/feuille à l'intérieur du document (ex: 'Feuille 1')
WORKSHEET_NAME = 'DATA' 
# IMPORTANT : Cette variable n'est plus utilisée, nous utilisons st.secrets à la place.
# CREDENTIALS_FILE = 'credentials.json' 

# --- DEFINITION DES COLONNES ---

# Colonnes de l'Excel (utilisées ici pour la vue et le filtrage)
EXCEL_COLUMNS_FOR_FILTER = ['NuméroAuto', 'Clôturé']

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

@st.cache_data(ttl=600) # Mise en cache des données pendant 10 minutes pour éviter des lectures répétées
def load_data_from_gsheet():
    """ 
    Lit la Google Sheet fusionnée, applique le filtre sur les lignes (non clôturées) 
    et le filtre sur les colonnes (vue application).
    """
    try:
        # --- CONNEXION SÉCURISÉE VIA STREAMLIT SECRETS ---
        
        # 1. Récupération des identifiants depuis st.secrets['gspread']
        secrets_immutable = st.secrets['gspread']
        
        # 2. CRÉATION D'UNE COPIE MODIFIABLE
        # On utilise 'creds' pour les credentials
        creds = dict(secrets_immutable)

        # -----------------------------------
        # --- BLOC DE DÉBOGAGE CRITIQUE ---
        # -----------------------------------
        print("DEBUG: Secrets gspread lus avec succès.")
        
        private_key_value = creds.get('private_key', 'CLE_MANQUANTE')
        
        if private_key_value == 'CLE_MANQUANTE':
            st.error("Erreur critique : La clé 'private_key' est absente de la section [gspread] des secrets.")
            return pd.DataFrame()
            
        print(f"DEBUG: Type de private_key AVANT conversion : {type(private_key_value)}")
        
        # 3. Réalignement de la clé privée pour gspread
        # On s'assure que la valeur est traitée comme une chaîne standard (str())
        # et on remplace SYSTEMATIQUEMENT les '\n' littéraux.
        # Nous faisons un .strip() de plus pour éliminer tout espace blanc invisible au début/fin
        private_key_value = str(private_key_value).strip()
        creds['private_key'] = private_key_value.replace('\\n', '\n')
        
        print(f"DEBUG: Type de private_key APRÈS conversion : {type(creds['private_key'])}")
        # -----------------------------------

        # 4. Connexion à gspread avec le dictionnaire modifié
        gc = gspread.service_account_from_dict(creds)

        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        # 1. Lecture de toutes les données fusionnées
        # st.spinner() affiche un message de chargement pendant l'exécution
        with st.spinner('Chargement des données de Google Sheets...'):
            # Utilisation de get_all_records pour lire les données sous forme de dictionnaire (plus robuste)
            df_full = pd.DataFrame(worksheet.get_all_records())

        # S'assurer que les en-têtes sont nettoyés
        df_full.columns = df_full.columns.str.strip()

        # 2. Préparation de la colonne de filtre 'Clôturé'
        if 'Clôturé' not in df_full.columns:
             st.error("Colonne 'Clôturé' manquante dans la Google Sheet. Impossible de filtrer les commandes ouvertes.")
             return pd.DataFrame() # Retourne un DataFrame vide en cas d'erreur
        
        df_full[KEY_COLUMN] = df_full[KEY_COLUMN].astype(str).str.strip()
        df_full['Clôturé'] = df_full['Clôturé'].astype(str).str.strip().str.upper()

        # 3. Filtrage des lignes: Ne garder que les commandes NON Clôturées
        df_open = df_full[df_full['Clôturé'] != 'OUI'].copy()
        
        # 4. Filtrage des colonnes: Ne garder que les colonnes nécessaires à l'Application
        df_app_view = df_open.reindex(columns=APP_VIEW_COLUMNS)
        
        # 5. Tri par NuméroAuto
        df_app_view = df_app_view.sort_values(by=KEY_COLUMN, ascending=True).reset_index(drop=True)
        
        st.success(f"Données chargées : {len(df_app_view)} commandes ouvertes prêtes.")
        return df_app_view

    except KeyError:
        # Cette erreur signifie que la section [gspread] est manquante dans les secrets Streamlit
        st.error("Erreur de configuration : Le secret Streamlit `gspread` est manquant. Veuillez le configurer dans les paramètres de l'application.")
        return pd.DataFrame()
    except Exception as e:
        # Erreur générale, affichage du message
        st.error(f"Erreur lors de la connexion/lecture de la Google Sheet. Vérifiez l'ID et les permissions du compte de service : {e}")
        return pd.DataFrame()


# --- 3. LOGIQUE ET AFFICHAGE STREAMLIT ---

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
        # Assurez-vous que les valeurs sont traitées comme des chaînes pour la comparaison
        df_filtered = df_filtered[df_filtered['StatutLivraison'].astype(str).str.strip() == selected_statut.strip()]
        
    # 4. Affichage des résultats
    st.subheader(f"Commandes Ouvertes Filtrées ({len(df_filtered)} / {len(df_data)})")

    # Utilisation de st.data_editor pour afficher le DataFrame
    # Note : La sortie de cette édition sera récupérée dans la prochaine étape pour la sauvegarde.
    st.data_editor(
        df_filtered,
        key="command_editor",
        height=500,
        use_container_width=True,
        hide_index=True,
        column_order=APP_VIEW_COLUMNS # Assure l'ordre des colonnes
    )

    # 5. Bouton de Rafraîchissement des données (pour recharger sans attendre le TTL du cache)
    if st.button("🔄 Rafraîchir les données (Recharger la GSheet)"):
        # st.cache_data.clear() vide le cache forçant la relecture de la feuille
        st.cache_data.clear()
        st.rerun() # Redémarre le script Streamlit pour recharger les données

if __name__ == '__main__':
    main()
