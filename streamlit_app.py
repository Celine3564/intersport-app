import pandas as pd
import gspread
import streamlit as st
import io 

# --- 1. CONFIGURATION ET CONSTANTES ---

# L'ID unique de votre feuille Google
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk' 
# Le nom exact de l'onglet/feuille à l'intérieur du document
WORKSHEET_NAME = 'DATA' 

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
# Liste de toutes les colonnes de la feuille (y compris Clôturé)
SHEET_REQUIRED_COLUMNS = [col.strip() for col in APP_VIEW_COLUMNS + ['Clôturé']]


# --- 2. FONCTION D'AUTHENTIFICATION ---
def authenticate_gsheet():
    """Authentifie et retourne l'objet gspread Client."""
    secrets_immutable = st.secrets['gspread']
    creds_for_auth = dict(secrets_immutable)
    
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
    Garantit que les colonnes manuelles sont du type str.
    """
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        with st.spinner('Chargement des données de Google Sheets...'):
            df_full = pd.DataFrame(worksheet.get_all_records())

        # Nettoyage et typage des colonnes
        df_full.columns = df_full.columns.str.strip()
        
        # Vérification des colonnes essentielles
        required_cols = [KEY_COLUMN, 'Clôturé'] + ESSENTIAL_EXCEL_COLUMNS
        for col in required_cols:
            if col not in df_full.columns:
                 st.error(f"Colonne essentielle '{col}' manquante dans la Google Sheet.")
                 return pd.DataFrame() # Retourne un DataFrame vide
        
        df_full[KEY_COLUMN] = df_full[KEY_COLUMN].astype(str).str.strip()
        df_full['Clôturé'] = df_full['Clôturé'].astype(str).str.strip().str.upper()

        # Garantir que toutes les colonnes manuelles sont de type string
        for col in APP_MANUAL_COLUMNS:
            if col in df_full.columns:
                df_full[col] = df_full[col].fillna('').astype(str).str.strip()
            # Si la colonne est manquante, elle sera ajoutée à vide plus tard.

        # Filtrage des commandes NON Clôturées
        df_open = df_full[df_full['Clôturé'] != 'OUI'].copy()
        
        # Filtrage des colonnes pour la vue App
        df_app_view = df_open.reindex(columns=APP_VIEW_COLUMNS)
        
        # Remplir les NaN/None dans les colonnes d'édition avec des chaînes vides
        df_app_view[APP_MANUAL_COLUMNS] = df_app_view[APP_MANUAL_COLUMNS].fillna('')
        
        df_app_view = df_app_view.sort_values(by=KEY_COLUMN, ascending=True).reset_index(drop=True)
        
        st.success(f"Données chargées : {len(df_app_view)} commandes ouvertes prêtes.")
        # Retourne uniquement le DataFrame filtré
        return df_app_view

    except ValueError as e:
        st.error(f"Erreur de configuration : {e}")
        return pd.DataFrame()
    except KeyError:
        st.error("Erreur de configuration : Le secret Streamlit `gspread` est manquant. Veuillez le configurer dans les paramètres de l'application.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur de connexion/lecture. Le problème est lié aux PERMISSIONS de la Google Sheet. Erreur: {e}")
        return pd.DataFrame()

# --- 4. LOGIQUE ET AFFICHAGE STREAMLIT ---
def main():
    st.set_page_config(
        page_title="Suivi des Commandes (Lecture Seule)",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    st.title("📦 Suivi des Commandes Ouvertes (Version Basique)")
    st.caption("Affiche les commandes NON Clôturées de la Google Sheet. L'édition est possible dans le tableau, mais les **modifications NE SONT PAS SAUVEGARDÉES** dans cette version simplifiée.")

    # 1. Chargement des données (avec mise en cache)
    df_data = load_data_from_gsheet()
    
    if df_data.empty:
        st.info("Aucune donnée n'a été chargée. Veuillez vérifier la connexion ou l'existence de commandes ouvertes.")
        return

    # 2. Affichage principal du tableau
    st.subheader(f"Commandes Ouvertes ({len(df_data)})")

    # Configuration des colonnes (pour désactiver les colonnes Excel de lecture seule)
    column_configs = {
        col: st.column_config.Column(
            col,
            disabled=(col not in APP_MANUAL_COLUMNS)
        ) for col in APP_VIEW_COLUMNS
    }
    
    # Éditeur de données
    # Le key "command_editor" est réintroduit pour capter la sélection.
    # on_select="rerun" a été explicitement retiré.
    edited_df = st.data_editor(
        df_data,
        key="command_editor", # Réintroduit le key pour capter la sélection
        height=500,
        use_container_width=True,
        hide_index=True,
        column_order=APP_VIEW_COLUMNS,
        column_config=column_configs,
        # IMPORTANT : L'édition est permise mais les données éditées NE SONT PAS utilisées ni sauvegardées.
    )

    # --- 3. Affichage des détails de la ligne sélectionnée ---
    
    # Vérifie si la sélection est présente et non vide
    selection_state = st.session_state.get("command_editor", {}).get("selection", {})
    selected_rows_indices = selection_state.get("rows", [])
    
    if selected_rows_indices:
        # Récupère l'index de la ligne sélectionnée dans le DF affiché
        selected_index = selected_rows_indices[0]
        
        try:
            # Accès direct à la ligne puisque l'application n'a pas de filtres
            selected_row_data = df_data.iloc[selected_index]
            
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

        except IndexError:
            st.info("Détails non affichés : Index de ligne invalide (sélection perdue).")
        except Exception as e:
            st.error(f"Erreur inattendue lors de l'affichage des détails : {e}")

    # --- 4. Bouton de Rafraîchissement seulement ---
    if st.button("🔄 Rafraîchir les données depuis Google Sheet"):
        st.cache_data.clear()
        st.rerun() 

if __name__ == '__main__':
    main()
