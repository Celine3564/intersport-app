import pandas as pd
import gspread
import streamlit as st
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# --- CONFIGURATION & CONSTANTES ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'

# Liste complète des colonnes pour assurer la cohérence du Google Sheet
COLUMNS_DATA = [
    'NumReception', 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Livré le', 'Qté', 'Collection', 'Num Facture', 'StatutBL', 
    'Emplacement', 'NomDeballage', 'Date Clôture', 'LitigesCompta', 
    'Commentaire_litige', 'NumTransport'
]

# --- FONCTIONS TECHNIQUES ---

def authenticate_gsheet():
    """Authentification via Streamlit Secrets"""
    creds = dict(st.secrets['gspread'])
    creds['private_key'] = creds['private_key'].replace('\\n', '\n')
    return gspread.service_account_from_dict(creds)

def load_data(ws_name, cols):
    """Chargement des données avec formatage des dates pour Ag-Grid"""
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(ws_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # Renommer si nécessaire pour correspondre à notre standard interne
        if 'Date Livré' in df.columns: 
            df = df.rename(columns={'Date Livré': 'Livré le'})
        
        # Conversion des colonnes temporelles
        for col in ['Livré le', 'Date Clôture']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        return df.reindex(columns=cols).fillna('')
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
        return pd.DataFrame(columns=cols)

def update_multiple_rows(df_changes):
    """Mise à jour multi-lignes optimisée"""
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_DATA)
        headers = ws.row_values(1)
        
        for _, row in df_changes.iterrows():
            # On cherche par NumReception (clé primaire)
            cell = ws.find(str(row['NumReception']), in_column=1)
            if cell:
                for col_name, val in row.items():
                    if col_name in headers and col_name != 'NumReception':
                        c_idx = headers.index(col_name) + 1
                        # Formatage date pour l'écriture dans Google Sheets
                        if isinstance(val, pd.Timestamp):
                            val = val.strftime('%Y-%m-%d')
                        ws.update_cell(cell.row, c_idx, str(val))
        return True
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")
        return False

# --- UI : COMPOSANT GRILLE ---

def render_advanced_grid(df, editable_cols=[]):
    """Génère une grille Ag-Grid avec filtres flottants et types de données"""
    gb = GridOptionsBuilder.from_dataframe(df)
    
    # Paramètres par défaut
    gb.configure_default_column(
        resizable=True, sortable=True, filterable=True, 
        editable=False, filter='agTextColumnFilter', floatingFilter=True
    )
    
    # Configuration spécifique des dates
    date_filter_params = {
        "comparator": """function(filterLocalDateAtMidnight, cellValue) {
            if (cellValue == null) return -1;
            var cellDate = new Date(cellValue);
            if (filterLocalDateAtMidnight.getTime() === cellDate.getTime()) return 0;
            if (cellDate < filterLocalDateAtMidnight) return -1;
            if (cellDate > filterLocalDateAtMidnight) return 1;
        }"""
    }
    
    for col in ['Livré le', 'Date Clôture']:
        if col in df.columns:
            gb.configure_column(
                col, 
                filter='agDateColumnFilter', 
                filterParams=date_filter_params,
                valueFormatter="x.value ? x.value.split('T')[0] : ''"
            )

    # Colonnes éditables (Mise en évidence)
    for col in editable_cols:
        gb.configure_column(
            col, editable=True, 
            cellStyle={'background-color': '#e0f2fe', 'border': '1px solid #38bdf8'}
        )

    gb.configure_pagination(paginationAutoPageSize=True)
    grid_options = gb.build()
    
    return AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        theme='balham',
        allow_unsafe_jscode=True,
        height=500
    )

# --- APPLICATION ---

def main():
    st.set_page_config(page_title="Logistique Intégrale", layout="wide")
    
    if 'page' not in st.session_state: st.session_state.page = '1'

    # Menu latéral complet
    with st.sidebar:
        st.header("📦 Menu Logistique")
        if st.button("📥 1. Import Excel", use_container_width=True): st.session_state.page = '1'
        if st.button("📍 2. Emplacements", use_container_width=True): st.session_state.page = '2'
        if st.button("⚙️ 3. Déballage & Litiges", use_container_width=True): st.session_state.page = '3'
        if st.button("🚚 4. Suivi Transport", use_container_width=True): st.session_state.page = '4'
        if st.button("⚠️ 5. Pas de Commande", use_container_width=True): st.session_state.page = '5'
        st.markdown("---")
        if st.button("📜 Historique Global", use_container_width=True): st.session_state.page = 'hist'

    # --- PAGE 1 : IMPORT EXCEL ---
    if st.session_state.page == '1':
        st.header("📥 Import des nouvelles réceptions")
        uploaded_file = st.file_uploader("Choisir le fichier d'extraction Excel", type=['xlsx', 'xls'])
        
        if uploaded_file:
            df_upload = pd.read_excel(uploaded_file)
            st.info(f"Fichier chargé : {len(df_upload)} lignes détectées.")
            
            # Contrôle de validité
            required_cols = ['NumReception', 'Fournisseur', 'Livré le']
            missing = [c for c in required_cols if c not in df_upload.columns]
            
            if missing:
                st.error(f"Erreur : Les colonnes suivantes sont absentes : {', '.join(missing)}")
            else:
                st.write("Aperçu avant envoi :")
                st.dataframe(df_upload.head())
                
                if st.button("🚀 Valider et Envoyer vers Google Sheets"):
                    with st.spinner("Envoi en cours..."):
                        gc = authenticate_gsheet()
                        sh = gc.open_by_key(SHEET_ID)
                        ws = sh.worksheet(WS_DATA)
                        
                        df_final = df_upload.reindex(columns=COLUMNS_DATA).fillna('')
                        # Convertir dates en texte
                        for c in ['Livré le', 'Date Clôture']:
                            if c in df_final.columns:
                                df_final[c] = df_final[c].astype(str).replace(['NaT', 'nan'], '')
                        
                        ws.append_rows(df_final.values.tolist())
                        st.success("✅ Importation terminée !")

    # --- PAGE 2 : EMPLACEMENTS ---
    elif st.session_state.page == '2':
        st.header("📍 Attribution des Emplacements")
        df_all = load_data(WS_DATA, COLUMNS_DATA)
        # On ne traite que ce qui n'est pas clôturé et sans emplacement
        df_target = df_all[(df_all['StatutBL'] != 'Clôturé') & (df_all['Emplacement'] == '')].copy()

        if df_target.empty:
            st.success("Toutes les réceptions ont un emplacement !")
        else:
            st.info("Saisissez l'emplacement puis cliquez sur Sauvegarder.")
            grid_res = render_advanced_grid(
                df_target[['NumReception', 'Fournisseur', 'Livré le', 'Qté', 'Emplacement']],
                editable_cols=['Emplacement']
            )
            if st.button("💾 Sauvegarder les Emplacements"):
                if update_multiple_rows(grid_res['data']):
                    st.success("Données enregistrées.")
                    st.rerun()

    # --- PAGE 3 : DÉBALLAGE & LITIGES ---
    elif st.session_state.page == '3':
        st.header("⚙️ Suivi du Déballage & Gestion des Litiges")
        df_all = load_data(WS_DATA, COLUMNS_DATA)
        # On filtre pour exclure les dossiers clôturés
        df_target = df_all[df_all['StatutBL'] != 'Clôturé'].copy()
        
        st.warning("Gérez ici les statuts, les noms des déballeurs et les commentaires de litige.")
        grid_res = render_advanced_grid(
            df_target[['NumReception', 'Fournisseur', 'StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige']],
            editable_cols=['StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige']
        )
        
        if st.button("💾 Enregistrer les Modifications"):
            if update_multiple_rows(grid_res['data']):
                st.success("Mise à jour effectuée.")
                st.rerun()

    # --- PAGE 4 : SUIVI TRANSPORT ---
    elif st.session_state.page == '4':
        st.header("🚚 Suivi des Transports")
        df_all = load_data(WS_DATA, COLUMNS_DATA)
        # On affiche tout ce qui est récent ou en cours
        df_target = df_all.copy()
        
        st.info("Ajoutez ou modifiez les numéros de transport ici.")
        grid_res = render_advanced_grid(
            df_target[['NumReception', 'Fournisseur', 'Livré le', 'NumTransport', 'StatutBL']],
            editable_cols=['NumTransport']
        )
        
        if st.button("💾 Enregistrer les Numéros de Transport"):
            if update_multiple_rows(grid_res['data']):
                st.success("Transports mis à jour.")
                st.rerun()

    # --- PAGE 5 : PAS DE COMMANDE ---
    elif st.session_state.page == '5':
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

    # --- PAGE HISTORIQUE ---
    elif st.session_state.page == 'hist':
        st.header("📜 Historique Complet (Lecture seule)")
        df_all = load_data(WS_DATA, COLUMNS_DATA)
        render_advanced_grid(df_all)

if __name__ == "__main__":
    main()import pandas as pd
import gspread
import streamlit as st
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# --- CONFIGURATION & CONSTANTES ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
COLUMNS_DATA = [
    'NumReception', 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Livré le', 'Qté', 'Collection', 'Num Facture', 'StatutBL', 
    'Emplacement', 'NomDeballage', 'Date Clôture', 'LitigesCompta', 
    'Commentaire_litige', 'NumTransport'
]

# --- FONCTIONS TECHNIQUES ---

def authenticate_gsheet():
    creds = dict(st.secrets['gspread'])
    creds['private_key'] = creds['private_key'].replace('\\n', '\n')
    return gspread.service_account_from_dict(creds)

def load_data(ws_name, cols):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(ws_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # Harmonisation du nom de la colonne date
        if 'Date Livré' in df.columns: 
            df = df.rename(columns={'Date Livré': 'Livré le'})
        
        # Conversion forcée en datetime pour les filtres Ag-Grid
        for col in ['Livré le', 'Date Clôture']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        return df.reindex(columns=cols).fillna('')
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
        return pd.DataFrame(columns=cols)

def update_multiple_rows(df_changes):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_DATA)
        headers = ws.row_values(1)
        
        for _, row in df_changes.iterrows():
            cell = ws.find(str(row['NumReception']), in_column=1)
            if cell:
                for col_name, val in row.items():
                    if col_name in headers and col_name != 'NumReception':
                        c_idx = headers.index(col_name) + 1
                        if isinstance(val, pd.Timestamp):
                            val = val.strftime('%Y-%m-%d')
                        ws.update_cell(cell.row, c_idx, str(val))
        return True
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")
        return False

# --- UI : GRILLE AG-GRID AVEC FILTRES EXCEL ---

def render_advanced_grid(df, editable_cols=[]):
    gb = GridOptionsBuilder.from_dataframe(df)
    
    # Configuration par défaut : Filtre texte + Barre flottante (recherche directe sous l'en-tête)
    gb.configure_default_column(
        resizable=True, sortable=True, filterable=True, 
        editable=False, filter='agTextColumnFilter', floatingFilter=True
    )
    
    # Configuration spécifique pour les DATES (Sélecteur calendrier)
    date_filter_params = {
        "comparator": """function(filterLocalDateAtMidnight, cellValue) {
            if (cellValue == null) return -1;
            var cellDate = new Date(cellValue);
            if (filterLocalDateAtMidnight.getTime() === cellDate.getTime()) return 0;
            if (cellDate < filterLocalDateAtMidnight) return -1;
            if (cellDate > filterLocalDateAtMidnight) return 1;
        }"""
    }
    
    for col in ['Livré le', 'Date Clôture']:
        if col in df.columns:
            gb.configure_column(
                col, 
                filter='agDateColumnFilter', 
                filterParams=date_filter_params,
                valueFormatter="x.value ? x.value.split('T')[0] : ''"
            )

    # Colonnes éditables (Style visuel bleu)
    for col in editable_cols:
        gb.configure_column(
            col, editable=True, 
            cellStyle={'background-color': '#f0f9ff', 'border': '1px solid #0ea5e9'}
        )

    gb.configure_pagination(paginationAutoPageSize=True)
    grid_options = gb.build()
    
    return AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        theme='balham',
        allow_unsafe_jscode=True,
        height=500
    )

# --- APPLICATION PRINCIPALE ---

def main():
    st.set_page_config(page_title="NozyLog Pro", layout="wide")
    
    if 'page' not in st.session_state: st.session_state.page = '1'

    # Barre latérale
    with st.sidebar:
        st.title("📦 NozyLog")
        st.markdown("---")
        if st.button("📥 1. Import Excel", use_container_width=True): st.session_state.page = '1'
        if st.button("📍 2. Emplacement", use_container_width=True): st.session_state.page = '2'
        if st.button("⚙️ 3. Déballage", use_container_width=True): st.session_state.page = '3'
        if st.button("📜 Historique", use_container_width=True): st.session_state.page = 'hist'

    # --- PAGE 1 : IMPORT EXCEL (RESTAURÉE) ---
    if st.session_state.page == '1':
        st.header("📥 Import des nouvelles réceptions")
        uploaded_file = st.file_uploader("Choisir un fichier Excel", type=['xlsx', 'xls'])
        
        if uploaded_file:
            df_upload = pd.read_excel(uploaded_file)
            st.write("Aperçu des données :")
            st.dataframe(df_upload.head())
            
            # Contrôle des colonnes
            missing_cols = [c for c in COLUMNS_DATA[:8] if c not in df_upload.columns]
            
            if missing_cols:
                st.error(f"Colonnes manquantes : {', '.join(missing_cols)}")
            else:
                if st.button("🚀 Envoyer vers Google Sheets"):
                    try:
                        gc = authenticate_gsheet()
                        sh = gc.open_by_key(SHEET_ID)
                        ws = sh.worksheet(WS_DATA)
                        
                        # Préparation des données (on complète les colonnes vides)
                        df_final = df_upload.reindex(columns=COLUMNS_DATA).fillna('')
                        # Conversion dates en texte pour l'envoi
                        for col in ['Livré le', 'Date Clôture']:
                            df_final[col] = df_final[col].astype(str).replace('NaT', '')
                            
                        ws.append_rows(df_final.values.tolist())
                        st.success(f"✅ {len(df_final)} lignes ajoutées avec succès !")
                    except Exception as e:
                        st.error(f"Erreur technique : {e}")

    # --- PAGE 2 : EMPLACEMENT ---
    elif st.session_state.page == '2':
        st.header("📍 Attribution des Emplacements")
        df_all = load_data(WS_DATA, COLUMNS_DATA)
        df_target = df_all[(df_all['StatutBL'] != 'Clôturé') & (df_all['Emplacement'] == '')].copy()

        if df_target.empty:
            st.info("Aucune réception en attente d'emplacement.")
        else:
            st.warning("Double-cliquez sur la cellule 'Emplacement' pour modifier.")
            grid_res = render_advanced_grid(
                df_target[['NumReception', 'Fournisseur', 'Livré le', 'Qté', 'Emplacement']],
                editable_cols=['Emplacement']
            )
            
            if st.button("💾 Enregistrer les emplacements"):
                if update_multiple_rows(grid_res['data']):
                    st.success("Emplacements mis à jour !")
                    st.rerun()

    # --- PAGE 3 : DÉBALLAGE ---
    elif st.session_state.page == '3':
        st.header("⚙️ Suivi du Déballage")
        df_all = load_data(WS_DATA, COLUMNS_DATA)
        df_target = df_all[df_all['StatutBL'].isin(['À déballer', 'LITIGE', 'En cours', ''])].copy()
        
        grid_res = render_advanced_grid(
            df_target[['NumReception', 'Fournisseur', 'Emplacement', 'StatutBL', 'NomDeballage', 'Commentaire_litige']],
            editable_cols=['StatutBL', 'NomDeballage', 'Commentaire_litige']
        )
        
        if st.button("💾 Valider les modifications"):
            if update_multiple_rows(grid_res['data']):
                st.success("Statuts mis à jour.")
                st.rerun()

    # --- PAGE HISTORIQUE ---
    elif st.session_state.page == 'hist':
        st.header("📜 Historique Global")
        df_all = load_data(WS_DATA, COLUMNS_DATA)
        render_advanced_grid(df_all)

if __name__ == "__main__":
    main()
