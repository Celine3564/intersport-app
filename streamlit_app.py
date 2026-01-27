import pandas as pd
import gspread
import streamlit as st
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# --- CONFIGURATION ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
# Liste exhaustive des colonnes
COLUMNS_DATA = [
    'NumReception', 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Livré le', 'Qté', 'Collection', 'Num Facture', 'StatutBL', 
    'Emplacement', 'NomDeballage', 'Date Clôture', 'LitigesCompta', 
    'Commentaire_litige', 'NumTransport'
]

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
        
        # Nettoyage des noms de colonnes et gestion des dates
        if 'Date Livré' in df.columns: 
            df = df.rename(columns={'Date Livré': 'Livré le'})
        
        # Conversion des colonnes de dates en objets datetime pour le filtre Ag-Grid
        date_cols = ['Livré le', 'Date Clôture']
        for col in date_cols:
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
                        # Conversion date en string pour GSheet si c'est un timestamp
                        if isinstance(val, pd.Timestamp):
                            val = val.strftime('%Y-%m-%d')
                        ws.update_cell(cell.row, c_idx, str(val))
        return True
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")
        return False

# --- CONFIGURATION DU TABLEAU AVEC FILTRES AVANCÉS ---
def render_excel_grid(df, editable_cols=[]):
    gb = GridOptionsBuilder.from_dataframe(df)
    
    # 1. Configuration par défaut (Filtres textuels partout avec barre flottante)
    gb.configure_default_column(
        resizable=True,
        sortable=True,
        filterable=True,
        editable=False,
        filter='agTextColumnFilter',
        floatingFilter=True, 
    )
    
    # 2. Configuration spécifique pour les colonnes de DATE
    date_filter_params = {
        "comparator": """function(filterLocalDateAtMidnight, cellValue) {
            if (cellValue == null) return -1;
            var dateParts = cellValue.split("-");
            var cellDate = new Date(Number(dateParts[0]), Number(dateParts[1]) - 1, Number(dateParts[2]));
            if (filterLocalDateAtMidnight.getTime() === cellDate.getTime()) return 0;
            if (cellDate < filterLocalDateAtMidnight) return -1;
            if (cellDate > filterLocalDateAtMidnight) return 1;
        }"""
    }
    
    date_columns = ['Livré le', 'Date Clôture']
    for col in date_columns:
        if col in df.columns:
            gb.configure_column(
                col, 
                filter='agDateColumnFilter', 
                filterParams=date_filter_params,
                valueFormatter="x.value ? x.value.split('T')[0] : ''" # Affiche uniquement YYYY-MM-DD
            )

    # 3. Configuration des colonnes éditables
    for col in editable_cols:
        gb.configure_column(
            col, 
            editable=True, 
            cellStyle={'background-color': '#e1f5fe', 'border': '1px solid #01579b'}
        )

    # Options de pagination et sélection
    gb.configure_pagination(paginationAutoPageSize=True)
    gb.configure_selection('single', use_checkbox=False)
    
    grid_options = gb.build()
    
    return AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=False, # False pour permettre le défilement horizontal si bcp de cols
        theme='balham', 
        allow_unsafe_jscode=True,
        height=500
    )

def main():
    st.set_page_config(page_title="NozyLog - AgGrid Advanced Filters", layout="wide")
    
    if 'page' not in st.session_state: st.session_state.page = '2'

    with st.sidebar:
        st.title("📦 NozyLog")
        st.markdown("---")
        if st.button("📍 2. Emplacement", use_container_width=True): st.session_state.page = '2'
        if st.button("⚙️ 3. Déballage", use_container_width=True): st.session_state.page = '3'
        if st.button("📜 Historique", use_container_width=True): st.session_state.page = 'hist'

    df_all = load_data(WS_DATA, COLUMNS_DATA)

    if st.session_state.page == '2':
        st.subheader("📍 Attribution des Emplacements")
        # Filtrage : On montre ce qui n'a pas encore d'emplacement
        df_target = df_all[(df_all['StatutBL'] != 'Clôturé') & (df_all['Emplacement'] == '')].copy()

        if df_target.empty:
            st.success("Toutes les réceptions ont un emplacement.")
        else:
            st.info("Filtrez par date ou par fournisseur via les sélecteurs sous les titres.")
            grid_res = render_excel_grid(
                df_target[['NumReception', 'Fournisseur', 'Livré le', 'Qté', 'Emplacement']],
                editable_cols=['Emplacement']
            )
            
            if st.button("💾 Sauvegarder les emplacements"):
                if update_multiple_rows(grid_res['data']):
                    st.success("Mise à jour réussie !")
                    st.rerun()

    elif st.session_state.page == '3':
        st.subheader("⚙️ Zone de Déballage")
        df_target = df_all[df_all['StatutBL'].isin(['À déballer', 'LITIGE', 'En cours'])].copy()
        
        grid_res = render_excel_grid(
            df_target[['NumReception', 'Fournisseur', 'Emplacement', 'StatutBL', 'NomDeballage', 'Commentaire_litige']],
            editable_cols=['StatutBL', 'NomDeballage', 'Commentaire_litige']
        )
        
        if st.button("🚀 Valider les modifications"):
            if update_multiple_rows(grid_res['data']):
                st.success("Données enregistrées.")
                st.rerun()

    elif st.session_state.page == 'hist':
        st.subheader("📜 Historique complet")
        render_excel_grid(df_all)

if __name__ == "__main__":
    main()
