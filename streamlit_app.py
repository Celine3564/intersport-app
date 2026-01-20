import pandas as pd
import gspread
import streamlit as st
from datetime import datetime

# --- CONFIGURATION ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
WS_TRANSPORT = 'TRANSPORT'

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
        if 'DateDebutDeballage' in df.columns: df = df.rename(columns={'DateDebutDeballage': 'Date Clôture'})
        if 'NumReception' in df.columns: df['NumReception'] = df['NumReception'].astype(str)
        return df.reindex(columns=cols).fillna('')
    except:
        return pd.DataFrame(columns=cols)

def save_new_rows(ws_name, df):
    if df.empty: return True
    gc = authenticate_gsheet()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ws_name)
    ws.append_rows(df.values.tolist(), value_input_option='USER_ENTERED')
    return True

def update_single_row(reception_id, updates):
    gc = authenticate_gsheet()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(WS_DATA)
    headers = ws.row_values(1)
    try:
        cell = ws.find(str(reception_id), in_column=1)
        for col_name, val in updates.items():
            if col_name in headers:
                c_idx = headers.index(col_name) + 1
                ws.update_cell(cell.row, c_idx, str(val))
        return True
    except:
        return False

# --- INTERFACE ---
def main():
    st.set_page_config(page_title="NozyLog", layout="wide")
    
    if 'page' not in st.session_state: st.session_state.page = '1'
    if 'last_imported' not in st.session_state: st.session_state.last_imported = []

    with st.sidebar:
        st.title("📦 NozyLog")
        if st.button("1️⃣ Import Fichier"): st.session_state.page = '1'
        if st.button("2️⃣ Emplacement"): st.session_state.page = '2'
        if st.button("3️⃣ Déballage"): st.session_state.page = '3'
        st.divider()
        if st.button("🚛 Transport"): st.session_state.page = 'trans'
        if st.button("📜 Historique"): st.session_state.page = 'hist'
        if st.button("⚠️ Litiges"): st.session_state.page = 'compta'

    df_all = load_data(WS_DATA, COLUMNS_DATA)

    # --- PAGE 1 : IMPORT ---
    if st.session_state.page == '1':
        st.header("1️⃣ Importation")
        up = st.file_uploader("Fichier Nozymag", type=['xlsx'])
        if up and st.button("Lancer l'importation"):
            df_new = pd.read_excel(up)
            df_new.columns = df_new.columns.str.strip()
            if 'NumeroAuto' in df_new.columns: df_new = df_new.rename(columns={'NumeroAuto': 'NumReception'})
            df_new['NumReception'] = df_new['NumReception'].astype(str)
            existing_ids = set(df_all['NumReception'].astype(str))
            df_to_add = df_new[~df_new['NumReception'].isin(existing_ids)].copy()
            if not df_to_add.empty:
                df_to_add['StatutBL'] = 'À déballer'
                for c in COLUMNS_DATA: 
                    if c not in df_to_add.columns: df_to_add[c] = ''
                save_new_rows(WS_DATA, df_to_add[COLUMNS_DATA])
                st.session_state.last_imported = df_to_add['NumReception'].tolist()
                st.rerun()

        if st.session_state.last_imported:
            st.subheader("Dernier import")
            st.dataframe(df_all[df_all['NumReception'].isin(st.session_state.last_imported)], hide_index=True)

    # --- PAGE 2 : EMPLACEMENT ---
    elif st.session_state.page == '2':
        st.header("2️⃣ Saisie d'emplacement")
        
        # Filtre de recherche
        search_query = st.text_input("🔍 Rechercher un Fournisseur ou N° Réception :", "").lower()
        
        df_no_loc = df_all[(df_all['StatutBL'] == 'À déballer') & (df_all['Emplacement'].astype(str).str.strip() == '')]
        
        if search_query:
            df_no_loc = df_no_loc[
                df_no_loc['Fournisseur'].str.lower().str.contains(search_query) | 
                df_no_loc['NumReception'].str.lower().str.contains(search_query)
            ]

        if df_no_loc.empty:
            st.success("Aucune réception correspondante en attente d'emplacement.")
        else:
            st.info("💡 Astuce : Survolez le tableau pour utiliser la loupe de recherche interne.")
            edited = st.data_editor(
                df_no_loc[['NumReception', 'Fournisseur', 'Livré le', 'Emplacement']],
                key="loc_editor", hide_index=True, use_container_width=True
            )
            if st.button("💾 Enregistrer les emplacements"):
                changes = st.session_state["loc_editor"].get("edited_rows", {})
                for idx_str, val in changes.items():
                    rid = df_no_loc.iloc[int(idx_str)]['NumReception']
                    update_single_row(rid, val)
                st.rerun()

    # --- PAGE 3 : DEBALLAGE ---
    elif st.session_state.page == '3':
        st.header("3️⃣ Déballage en cours")
        
        # Filtre de recherche
        search_query = st.text_input("🔍 Rechercher par Fournisseur, Emplacement ou N° :", "").lower()
        
        df_work = df_all[df_all['StatutBL'].isin(['À déballer', 'LITIGE'])].copy()
        
        if search_query:
            df_work = df_work[
                df_work['Fournisseur'].str.lower().str.contains(search_query) | 
                df_work['NumReception'].str.lower().str.contains(search_query) |
                df_work['Emplacement'].str.lower().str.contains(search_query)
            ]
        
        if df_work.empty:
            st.info("Aucun déballage correspondant à votre recherche.")
        else:
            st.write("Cochez 'Terminer' ou 'Litige' pour mettre à jour.")
            
            df_work['✅ Terminer'] = False
            df_work['⚠️ Litige'] = False
            
            cols_to_show = ['NumReception', 'Fournisseur', 'Emplacement', 'NomDeballage', 'Commentaire_litige', '✅ Terminer', '⚠️ Litige']
            
            edited_df = st.data_editor(
                df_work[cols_to_show],
                key="deb_editor",
                hide_index=True,
                use_container_width=True,
                disabled=['NumReception', 'Fournisseur', 'Emplacement']
            )
            
            if st.button("🚀 Valider les actions"):
                changes = st.session_state["deb_editor"].get("edited_rows", {})
                count = 0
                for idx_str, val in changes.items():
                    row_idx = int(idx_str)
                    rid = df_work.iloc[row_idx]['NumReception']
                    
                    update_data = {}
                    if val.get('✅ Terminer') == True:
                        update_data = {
                            'StatutBL': 'Clôturée',
                            'NomDeballage': val.get('NomDeballage', df_work.iloc[row_idx]['NomDeballage']),
                            'Date Clôture': datetime.now().strftime('%d/%m/%Y')
                        }
                    elif val.get('⚠️ Litige') == True:
                        update_data = {
                            'StatutBL': 'LITIGE',
                            'NomDeballage': val.get('NomDeballage', df_work.iloc[row_idx]['NomDeballage']),
                            'Commentaire_litige': val.get('Commentaire_litige', df_work.iloc[row_idx]['Commentaire_litige'])
                        }
                    elif 'NomDeballage' in val or 'Commentaire_litige' in val:
                        update_data = val
                    
                    if update_data:
                        update_single_row(rid, update_data)
                        count += 1
                
                if count > 0:
                    st.success(f"{count} ligne(s) mise(s) à jour !")
                    st.rerun()

    elif st.session_state.page == 'hist':
        st.header("📜 Historique")
        search_query = st.text_input("🔍 Rechercher dans l'historique :", "").lower()
        df_hist = df_all[df_all['StatutBL'] == 'Clôturée']
        if search_query:
            df_hist = df_hist[df_hist.apply(lambda row: search_query in row.astype(str).str.lower().values, axis=1)]
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

    elif st.session_state.page == 'compta':
        st.header("⚠️ Litiges")
        search_query = st.text_input("🔍 Rechercher dans les litiges :", "").lower()
        df_lit = df_all[df_all['StatutBL'] == 'LITIGE']
        if search_query:
            df_lit = df_lit[df_lit.apply(lambda row: search_query in row.astype(str).str.lower().values, axis=1)]
        st.dataframe(df_lit, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
