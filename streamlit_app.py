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

COLUMNS_TRANSPORT = [
    'NumTransport', 'Magasin', 'NomTransporteur', 'NbPalettes', 
    'Poids_total', 'Commentaire_Livraison', 'Colis_manquant/abimé/ouvert', 'LitigeReception'
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
        
        # S'assurer que les IDs sont bien des strings pour les comparaisons
        if 'NumReception' in df.columns:
            df['NumReception'] = df['NumReception'].astype(str)
            
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

    # Sidebar Navigation
    with st.sidebar:
        st.title("📦 NozyLog")
        if st.button("1️⃣ Import Fichier"): st.session_state.page = '1'
        if st.button("2️⃣ Saisie Emplacement"): st.session_state.page = '2'
        if st.button("3️⃣ Déballage"): st.session_state.page = '3'
        st.divider()
        if st.button("🚛 Transport"): st.session_state.page = 'trans'
        if st.button("📜 Historique"): st.session_state.page = 'hist'
        if st.button("⚠️ Litiges"): st.session_state.page = 'compta'

    # Chargement frais des données (sans cache pour l'étape d'import)
    df_all = load_data(WS_DATA, COLUMNS_DATA)

    # --- PARTIE 1 : IMPORT ---
    if st.session_state.page == '1':
        st.header("1️⃣ Import du fichier Excel")
        up = st.file_uploader("Choisir le fichier Nozymag", type=['xlsx'])
        
        if up:
            if st.button("Lancer l'importation"):
                df_new = pd.read_excel(up)
                df_new.columns = df_new.columns.str.strip()
                
                # Mapping
                if 'NumeroAuto' in df_new.columns: df_new = df_new.rename(columns={'NumeroAuto': 'NumReception'})
                if 'Date Livré' in df_new.columns: df_new = df_new.rename(columns={'Date Livré': 'Livré le'})
                
                # Conversion forcée en string pour éviter les bugs de comparaison
                df_new['NumReception'] = df_new['NumReception'].astype(str)
                existing_ids = set(df_all['NumReception'].astype(str))
                
                df_to_add = df_new[~df_new['NumReception'].isin(existing_ids)].copy()
                
                if not df_to_add.empty:
                    df_to_add['StatutBL'] = 'À déballer'
                    for c in COLUMNS_DATA: 
                        if c not in df_to_add.columns: df_to_add[c] = ''
                    
                    save_new_rows(WS_DATA, df_to_add[COLUMNS_DATA])
                    # On stocke les IDs en string
                    st.session_state.last_imported = df_to_add['NumReception'].tolist()
                    st.success(f"{len(df_to_add)} lignes importées !")
                    st.rerun() # Recharger pour que df_all contienne les nouvelles lignes
                else:
                    st.warning("Aucune nouvelle donnée (doublons détectés).")

        # Affichage du tableau
        if st.session_state.last_imported:
            st.subheader("Données de l'import actuel")
            # Filtrage précis en forçant le type string
            view_df = df_all[df_all['NumReception'].astype(str).isin(st.session_state.last_imported)]
            if view_df.empty:
                st.error("Données enregistrées mais non trouvées à l'affichage. Veuillez rafraîchir la page.")
            else:
                st.dataframe(view_df, use_container_width=True, hide_index=True)
        else:
            st.info("Le tableau est vide. Veuillez importer un fichier Excel.")

    # --- PARTIE 2 : EMPLACEMENT ---
    elif st.session_state.page == '2':
        st.header("2️⃣ Saisie d'emplacement")
        df_no_loc = df_all[(df_all['StatutBL'] == 'À déballer') & (df_all['Emplacement'].astype(str).str.strip() == '')]
        
        if df_no_loc.empty:
            st.success("Toutes les réceptions ont un emplacement.")
        else:
            st.write("Réceptions en attente d'emplacement :")
            edited = st.data_editor(
                df_no_loc[['NumReception', 'Magasin', 'Fournisseur', 'Livré le', 'Emplacement']],
                key="loc_editor", hide_index=True, use_container_width=True
            )
            if st.button("Enregistrer les emplacements"):
                changes = st.session_state["loc_editor"].get("edited_rows", {})
                for idx_str, val in changes.items():
                    rid = df_no_loc.iloc[int(idx_str)]['NumReception']
                    update_single_row(rid, val)
                st.success("Enregistré !")
                st.rerun()

    # --- PARTIE 3 : DEBALLAGE ---
    elif st.session_state.page == '3':
        st.header("3️⃣ Déballage")
        df_deb = df_all[df_all['StatutBL'].isin(['À déballer', 'LITIGE'])]
        
        if df_deb.empty:
            st.info("Aucun déballage en cours.")
        else:
            for _, row in df_deb.iterrows():
                with st.expander(f"📦 {row['Fournisseur']} - {row['NumReception']} (Zone: {row['Emplacement']})"):
                    c1, c2 = st.columns(2)
                    with c1:
                        nom = st.text_input("Qui déballe ?", key=f"n_{row['NumReception']}", value=row['NomDeballage'])
                    with c2:
                        note = st.text_area("Commentaire", key=f"c_{row['NumReception']}", value=row['Commentaire_litige'])
                    
                    if st.button("✅ Terminer", key=f"ok_{row['NumReception']}"):
                        update_single_row(row['NumReception'], {
                            'StatutBL': 'Clôturée', 
                            'NomDeballage': nom, 
                            'Date Clôture': datetime.now().strftime('%d/%m/%Y')
                        })
                        st.rerun()

    # --- AUTRES PAGES ---
    elif st.session_state.page == 'trans':
        st.header("🚛 Transport")
        st.write("Utilisez le bouton 'Lier' pour associer des réceptions.")
        # ... (votre logique transport ici)

    elif st.session_state.page == 'hist':
        st.header("📜 Historique")
        st.dataframe(df_all[df_all['StatutBL'] == 'Clôturée'], use_container_width=True)

if __name__ == "__main__":
    main()
