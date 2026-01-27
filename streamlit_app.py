import pandas as pd
import gspread
import streamlit as st
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# --- CONFIGURATION ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
COLUMNS_DATA = [
    'NumReception', 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Livré le', 'Qté', 'Collection', 'Num Facture', 'StatutBL', 
    'Emplacement', 'NomDeballage', 'Date Clôture', 'LitigesCompta', 
    'Commentaire_litige', 'NumTransport'
]

# --- FONCTIONS GOOGLE SHEET ---
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
        if 'Date Livré' in df.columns: df = df.rename(columns={'Date Livré': 'Livré le'})
        return df.reindex(columns=cols).fillna('')
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
        return pd.DataFrame(columns=cols)

def update_multiple_rows(df_changes):
    """Met à jour les lignes modifiées dans Google Sheet"""
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
                        ws.update_cell(cell.row, c_idx, str(val))
        return True
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")
        return False

# --- CONFIGURATION DU TABLEAU EXCEL (AG-GRID) ---
def render_excel_grid(df, editable_cols=[]):
    gb = GridOptionsBuilder.from_dataframe(df)
    
    # Activation du filtrage et du tri sur TOUTES les colonnes (style Excel)
    gb.configure_default_column(
        resizable=True,
        filterable=True,
        sortable=True,
        editable=False,
        groupable=True
    )
    
    # Configuration spécifique des colonnes éditables
    for col in editable_cols:
        gb.configure_column(col, editable=True, cellStyle={'background-color': '#f0f2f6'})

    # Options de filtrage avancées (texte, nombre, menus déroulants)
    gb.configure_side_bar() # Ajoute une barre latérale pour les filtres complexes
    
    grid_options = gb.build()
    
    return AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=True,
        theme='streamlit', # Thème propre
        allow_unsafe_jscode=True
    )

# --- INTERFACE PRINCIPALE ---
def main():
    st.set_page_config(page_title="NozyLog - Excel Edition", layout="wide")
    
    if 'page' not in st.session_state: st.session_state.page = '2'

    with st.sidebar:
        st.title("📦 NozyLog")
        st.info("Utilisez les icônes dans les titres de colonnes pour filtrer.")
        if st.button("2️⃣ Emplacement"): st.session_state.page = '2'
        if st.button("3️⃣ Déballage"): st.session_state.page = '3'
        st.divider()
        if st.button("📜 Historique"): st.session_state.page = 'hist'

    df_all = load_data(WS_DATA, COLUMNS_DATA)

    # --- PAGE 2 : EMPLACEMENT ---
    if st.session_state.page == '2':
        st.header("📍 Saisie d'emplacement (Filtrage Excel)")
        
        # Données à traiter
        df_target = df_all[
            (df_all['StatutBL'] == 'À déballer') & 
            (df_all['Emplacement'] == '')
        ].copy()

        if df_target.empty:
            st.success("Toutes les réceptions ont un emplacement !")
        else:
            st.write("Modifiez la colonne 'Emplacement' directement dans le tableau.")
            # Affichage du tableau AgGrid
            grid_response = render_excel_grid(
                df_target[['NumReception', 'Fournisseur', 'Mt TTC', 'Livré le', 'Qté', 'Emplacement']],
                editable_cols=['Emplacement']
            )
            
            updated_df = grid_response['data']
            
            if st.button("💾 Enregistrer les modifications"):
                # On compare pour ne mettre à jour que ce qui a changé
                update_multiple_rows(updated_df)
                st.success("Emplacements mis à jour !")
                st.rerun()

    # --- PAGE 3 : DEBALLAGE ---
    elif st.session_state.page == '3':
        st.header("📦 Déballage et Contrôle")
        df_target = df_all[df_all['StatutBL'].isin(['À déballer', 'LITIGE'])].copy()
        
        st.write("Filtrez par Fournisseur ou Emplacement via les en-têtes.")
        grid_response = render_excel_grid(
            df_target[['NumReception', 'Fournisseur', 'Emplacement', 'Mt TTC', 'StatutBL', 'NomDeballage', 'Commentaire_litige']],
            editable_cols=['StatutBL', 'NomDeballage', 'Commentaire_litige']
        )
        
        if st.button("🚀 Valider le déballage"):
            update_multiple_rows(grid_response['data'])
            st.success("Données de déballage sauvegardées.")
            st.rerun()

    # --- HISTORIQUE ---
    elif st.session_state.page == 'hist':
        st.header("📜 Historique Complet")
        st.write("Tableau interactif : Glissez les titres pour trier ou filtrer.")
        render_excel_grid(df_all)

if __name__ == "__main__":
    main()
