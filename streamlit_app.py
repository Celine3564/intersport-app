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

def update_single_row(reception_id, updates):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_DATA)
        headers = ws.row_values(1)
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

    # --- PAGE 2 : EMPLACEMENT ---
    if st.session_state.page == '2':
        st.header("2️⃣ Saisie d'emplacement")
        
        search_query = st.text_input("🔍 Rechercher (Fournisseur, N°, Emplacement...) :", "").lower()
        
        # Filtre les lignes sans emplacement et en statut "À déballer"
        df_no_loc = df_all[(df_all['StatutBL'] == 'À déballer') & (df_all['Emplacement'].astype(str).str.strip() == '')].copy()
        
        if search_query:
            df_no_loc = df_no_loc[df_no_loc.apply(lambda row: search_query in row.astype(str).str.lower().values, axis=1)]

        if df_no_loc.empty:
            st.success("Aucune réception en attente d'emplacement.")
        else:
            st.info("💡 Modifiez la colonne 'Emplacement' directement dans le tableau ci-dessous.")
            
            # Colonnes demandées : N° Fourn., Mt TTC, Livré le, Qté + Emplacement
            cols_display = ['NumReception', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 'Livré le', 'Qté', 'Emplacement']
            
            edited = st.data_editor(
                df_no_loc[cols_display],
                key="loc_editor", 
                hide_index=True, 
                use_container_width=True,
                disabled=['NumReception', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 'Livré le', 'Qté']
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
        
        search_query = st.text_input("🔍 Rechercher un déballage (Mot-clé) :", "").lower()
        
        # Filtre les lignes en cours (À déballer ou Litige) ayant un emplacement
        df_work = df_all[
            (df_all['StatutBL'].isin(['À déballer', 'LITIGE'])) & 
            (df_all['Emplacement'].astype(str).str.strip() != '')
        ].copy()
        
        if search_query:
            df_work = df_work[df_work.apply(lambda row: search_query in row.astype(str).str.lower().values, axis=1)]
        
        if df_work.empty:
            st.info("Aucun déballage en cours ne correspond à votre recherche.")
        else:
            df_work['✅ Terminer'] = False
            df_work['⚠️ Litige'] = False
            
            # Intégration des colonnes demandées
            cols_display = [
                'NumReception', 'Fournisseur', 'Emplacement', 'N° Fourn.', 
                'Mt TTC', 'Livré le', 'Qté', 'NomDeballage', 
                'Commentaire_litige', '✅ Terminer', '⚠️ Litige'
            ]
            
            edited_df = st.data_editor(
                df_work[cols_display],
                key="deb_editor",
                hide_index=True,
                use_container_width=True,
                disabled=['NumReception', 'Fournisseur', 'Emplacement', 'N° Fourn.', 'Mt TTC', 'Livré le', 'Qté']
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
                    else:
                        if 'NomDeballage' in val: update_data['NomDeballage'] = val['NomDeballage']
                        if 'Commentaire_litige' in val: update_data['Commentaire_litige'] = val['Commentaire_litige']
                    
                    if update_data:
                        update_single_row(rid, update_data)
                        count += 1
                
                if count > 0:
                    st.success(f"{count} mise(s) à jour réussie(s) !")
                    st.rerun()

    # --- PAGES HISTORIQUE ET LITIGES (RESTE DU CODE) ---
    elif st.session_state.page == 'hist':
        st.header("📜 Historique des réceptions")
        search_query = st.text_input("🔍 Rechercher dans l'historique :", "").lower()
        df_hist = df_all[df_all['StatutBL'] == 'Clôturée']
        if search_query:
            df_hist = df_hist[df_hist.apply(lambda row: search_query in row.astype(str).str.lower().values, axis=1)]
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

    elif st.session_state.page == 'compta':
        st.header("⚠️ Gestion des Litiges")
        search_query = st.text_input("🔍 Rechercher un litige :", "").lower()
        df_lit = df_all[df_all['StatutBL'] == 'LITIGE']
        if search_query:
            df_lit = df_lit[df_lit.apply(lambda row: search_query in row.astype(str).str.lower().values, axis=1)]
        st.dataframe(df_lit, use_container_width=True, hide_index=True)

    elif st.session_state.page == '1':
        # (Page d'importation simplifiée ici pour la démo)
        st.header("1️⃣ Importation de fichier")
        st.write("Utilisez cette section pour charger vos nouveaux fichiers Nozymag.")

if __name__ == "__main__":
    main()
