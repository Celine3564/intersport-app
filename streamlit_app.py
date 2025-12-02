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
        
        # 2. CRÉATION D'UNE COPIE MODIFIABLE (Correction de l'erreur)
        # Ceci contourne l'erreur "Secrets does not support item assignment".
        secrets_mutable = dict(secrets_immutable)

        # 3. Réalignement de la clé privée pour gspread
        secrets_mutable['private_key'] = secrets_mutable['private_key'].replace('\\n', '\n')
        
        # 4. Connexion à gspread avec le dictionnaire modifié
        gc = gspread.service_account_from_dict(secrets_mutable)

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
        st.error("Erreur de configuration : Le secret Streamlit `gspread` est manquant. Veuillez le configurer dans
