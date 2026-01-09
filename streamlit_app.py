import pandas as pd
import gspread
import streamlit as st
from datetime import datetime

# --- CONFIGURATION ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
WS_TRANSPORT = 'TRANSPORT'

# Noms des colonnes mis à jour selon vos consignes
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

@st.cache_data(ttl=10)
def load_data(ws_name, cols):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(ws_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        # Gestion du renommage si les colonnes ont changé dans le sheet
        if 'Date Livré' in df.columns: df = df.rename(columns={'Date Livré': 'Livré le'})
        if 'DateDebutDeballage' in df.columns: df = df.rename(columns={'DateDebutDeballage': 'Date Clôture'})
        
        return df.reindex(columns=cols).fillna('')
    except:
        return pd.DataFrame(columns=cols)

def save_new_rows(ws_name, df):
    if df.empty: return True
    gc = authenticate_gsheet()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ws_name)
    ws.append_rows(df.values.tolist(), value_input_option='USER_ENTERED')
    st.cache_data.clear()
    return True

def update_single_row(reception_id, updates):
    gc = authenticate_gsheet()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(WS_DATA)
    headers = ws.row_values(1)
    try:
        cell = ws.find(str(reception_id), in_column=1)
        for col_name, val in updates.items():
            # Mapper les noms logiques aux têtes de colonnes réelles
            c_idx = headers.index(col_name) + 1
            ws.update_cell(cell.row, c_idx, str(val))
        st.cache_data.clear()
        return True
    except:
        return False

# --- LOGIQUE TRANSPORT ---
def get_next_transport_id():
    df_t = load_data(WS_TRANSPORT, COLUMNS_TRANSPORT)
    if df_t.empty: return "TR-001"
    ids = df_t['NumTransport'].astype(str).tolist()
    numeric_ids = []
    for i in ids:
        if i.startswith('TR-'):
            try: numeric_ids.append(int(i.split('-')[1]))
            except: pass
    next_num = max(numeric_ids, default=0) + 1
    return f"TR-{next_num:03d}"

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
        st.subheader("Autres")
        if st.button("🚛 Transport"): st.session_state.page = 'trans'
        if st.button("📜 Historique"): st.session_state.page = 'hist'
        if st.button("⚠️ Litige Compta"): st.session_state.page = 'compta'

    df_all = load_data(WS_DATA, COLUMNS_DATA)

    # --- PARTIE 1 : IMPORT ---
    if st.session_state.page == '1':
        st.header("1️⃣ Import du fichier Excel")
        up = st.file_uploader("Choisir le fichier Nozymag", type=['xlsx'])
        
        if up:
            if st.button("Lancer l'importation"):
                df_new = pd.read_excel(up)
                df_new.columns = df_new.columns.str.strip()
                # Mapping des colonnes sources
                if 'NumeroAuto' in df_new.columns: df_new = df_new.rename(columns={'NumeroAuto': 'NumReception'})
                if 'Date Livré' in df_new.columns: df_new = df_new.rename(columns={'Date Livré': 'Livré le'})
                
                existing_ids = set(df_all['NumReception'].astype(str))
                df_to_add = df_new[~df_new['NumReception'].astype(str).isin(existing_ids)].copy()
                
                if not df_to_add.empty:
                    df_to_add['StatutBL'] = 'À déballer'
                    for c in COLUMNS_DATA: 
                        if c not in df_to_add.columns: df_to_add[c] = ''
                    
                    save_new_rows(WS_DATA, df_to_add[COLUMNS_DATA])
                    st.session_state.last_imported = df_to_add['NumReception'].tolist()
                    st.success(f"{len(df_to_add)} nouvelles lignes importées !")
                else:
                    st.warning("Aucune nouvelle donnée trouvée dans le fichier.")

        # Affichage UNIQUEMENT des données importées (tableau vide à l'ouverture)
        if st.session_state.last_imported:
            st.subheader("Données de l'import actuel")
            view_df = df_all[df_all['NumReception'].isin(st.session_state.last_imported)]
            st.dataframe(view_df, use_container_width=True, hide_index=True)
        else:
            st.info("Le tableau est vide. Veuillez importer un fichier Excel.")

    # --- PARTIE 2 : EMPLACEMENT ---
    elif st.session_state.page == '2':
        st.header("2️⃣ Saisie d'emplacement")
        # Liste des réceptions qui n'ont pas d'emplacement
        df_no_loc = df_all[(df_all['StatutBL'] == 'À déballer') & (df_all['Emplacement'] == '')]
        
        if df_no_loc.empty:
            st.success("Toutes les réceptions ont un emplacement saisi.")
        else:
            st.write("Liste des réceptions sans emplacement :")
            edited = st.data_editor(
                df_no_loc[['NumReception', 'Magasin', 'Fournisseur', 'Livré le', 'Emplacement']],
                key="loc_editor", hide_index=True, use_container_width=True
            )
            if st.button("Enregistrer les emplacements"):
                changes = st.session_state["loc_editor"].get("edited_rows", {})
                for idx_str, val in changes.items():
                    rid = df_no_loc.iloc[int(idx_str)]['NumReception']
                    update_single_row(rid, val)
                st.rerun()

    # --- PARTIE 3 : DEBALLAGE ---
    elif st.session_state.page == '3':
        st.header("3️⃣ Déballage")
        # Liste simple des réceptions (priorité à celles qui ont un emplacement)
        df_deb = df_all[df_all['StatutBL'].isin(['À déballer', 'LITIGE'])]
        
        if df_deb.empty:
            st.info("Aucun déballage à effectuer.")
        else:
            for _, row in df_deb.iterrows():
                with st.expander(f"📦 {row['Fournisseur']} - {row['NumReception']} (Zone: {row['Emplacement']})"):
                    c1, c2 = st.columns(2)
                    with c1:
                        nom = st.text_input("Qui déballe ?", key=f"n_{row['NumReception']}", value=row['NomDeballage'])
                    with c2:
                        note = st.text_area("Commentaire (si litige)", key=f"c_{row['NumReception']}", value=row['Commentaire_litige'])
                    
                    b1, b2, _ = st.columns([1,1,2])
                    if b1.button("✅ Terminée", key=f"ok_{row['NumReception']}"):
                        update_single_row(row['NumReception'], {
                            'StatutBL': 'Clôturée', 
                            'NomDeballage': nom, 
                            'Date Clôture': datetime.now().strftime('%d/%m/%Y')
                        })
                        st.rerun()
                    if b2.button("⚠️ Litige", key=f"ko_{row['NumReception']}"):
                        update_single_row(row['NumReception'], {
                            'StatutBL': 'LITIGE', 
                            'NomDeballage': nom, 
                            'Commentaire_litige': note
                        })
                        st.rerun()

    # --- TRANSPORT ---
    elif st.session_state.page == 'trans':
        st.header("🚛 Transport")
        df_trans = load_data(WS_TRANSPORT, COLUMNS_TRANSPORT)
        
        # Création numéro auto
        st.subheader("Nouveau Numéro de Transport")
        next_id = get_next_transport_id()
        with st.form("new_transport"):
            c1, c2, c3 = st.columns(3)
            tid = c1.text_input("N° Transport", value=next_id)
            mag = c2.selectbox("Magasin", ["MAG1", "MAG2", "MAG3"])
            transp = c3.text_input("Transporteur")
            if st.form_submit_button("Créer et enregistrer"):
                save_new_rows(WS_TRANSPORT, pd.DataFrame([{'NumTransport': tid, 'Magasin': mag, 'NomTransporteur': transp}]))
                st.rerun()
        
        st.divider()
        # Liaison en rafale
        st.subheader("Réceptions non clôturées sans transport")
        df_pending = df_all[(df_all['StatutBL'] != 'Clôturée') & (df_all['NumTransport'] == '')]
        
        if not df_pending.empty:
            df_pending['Sélection'] = False
            sel = st.data_editor(df_pending[['Sélection', 'NumReception', 'Fournisseur', 'Livré le']], hide_index=True)
            
            target = st.selectbox("Assigner au Transport n°", options=df_trans['NumTransport'].unique())
            if st.button("Lier en rafale"):
                modifs = st.session_state[next(k for k in st.session_state if "data_editor" in k)].get("edited_rows", {})
                ids_to_update = []
                for idx_str, val in modifs.items():
                    if val.get('Sélection'):
                        ids_to_update.append(df_pending.iloc[int(idx_str)]['NumReception'])
                
                for rid in ids_to_update:
                    update_single_row(rid, {'NumTransport': target})
                st.rerun()

    # --- AUTRES PAGES ---
    elif st.session_state.page == 'hist':
        st.header("📜 Historique")
        st.dataframe(df_all[df_all['StatutBL'] == 'Clôturée'], use_container_width=True)

    elif st.session_state.page == 'compta':
        st.header("⚠️ Litiges Comptabilité")
        st.dataframe(df_all[df_all['StatutBL'] == 'LITIGE'], use_container_width=True)

if __name__ == "__main__":
    main()
