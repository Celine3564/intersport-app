import pandas as pd
import gspread
import streamlit as st
from datetime import datetime
import time

# --- CONFIGURATION ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
WS_TRANSPORT = 'TRANSPORT'

COLUMNS_DATA = [
    'NumReception', 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Date Livré', 'Qté', 'Collection', 'Num Facture', 'StatutBL', 
    'Emplacement', 'NomDeballage', 'DateDebutDeballage', 'LitigesCompta', 
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

@st.cache_data(ttl=60)
def load_data(ws_name, cols):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(ws_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
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

def update_multiple_rows(reception_ids, updates):
    gc = authenticate_gsheet()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(WS_DATA)
    headers = ws.row_values(1)
    
    for rid in reception_ids:
        try:
            cell = ws.find(str(rid), in_column=1)
            for col_name, val in updates.items():
                c_idx = headers.index(col_name) + 1
                ws.update_cell(cell.row, c_idx, str(val))
        except: continue
    st.cache_data.clear()
    return True

# --- LOGIQUE TRANSPORT ---
def get_next_transport_id(df_trans):
    if df_trans.empty or 'NumTransport' not in df_trans.columns:
        return "TR-001"
    ids = df_trans['NumTransport'].astype(str).tolist()
    numeric_ids = []
    for i in ids:
        if i.startswith('TR-'):
            try: numeric_ids.append(int(i.split('-')[1]))
            except: pass
    next_id = max(numeric_ids, default=0) + 1
    return f"TR-{next_id:03d}"

# --- INTERFACE ---
def main():
    st.set_page_config(page_title="NozyLog", layout="wide")
    
    if 'page' not in st.session_state: st.session_state.page = '1'

    # Sidebar Navigation
    with st.sidebar:
        st.title("📦 NozyLog v2")
        if st.button("1️⃣ Import & Emplacement"): st.session_state.page = '1'
        if st.button("2️⃣ Déballage"): st.session_state.page = '2'
        st.divider()
        if st.button("🚛 Transport"): st.session_state.page = 'trans'
        if st.button("⚠️ Litige Compta"): st.session_state.page = 'compta'
        if st.button("📜 Historique"): st.session_state.page = 'hist'

    df_data = load_data(WS_DATA, COLUMNS_DATA)

    # --- PAGE 1: IMPORT & EMPLACEMENT ---
    if st.session_state.page == '1':
        st.header("1️⃣ Import & Emplacement")
        
        up = st.file_uploader("Importer fichier Nozymag", type=['xlsx'])
        if up:
            if st.button("Confirmer l'import"):
                df_new = pd.read_excel(up)
                df_new.columns = df_new.columns.str.strip()
                # Mapping
                if 'NumeroAuto' in df_new.columns: df_new = df_new.rename(columns={'NumeroAuto': 'NumReception'})
                
                existing_ids = set(df_data['NumReception'].astype(str))
                df_to_add = df_new[~df_new['NumReception'].astype(str).isin(existing_ids)].copy()
                
                if not df_to_add.empty:
                    df_to_add['StatutBL'] = 'A_DEBALLER'
                    for c in COLUMNS_DATA: 
                        if c not in df_to_add.columns: df_to_add[c] = ''
                    save_new_rows(WS_DATA, df_to_add[COLUMNS_DATA])
                    st.success(f"{len(df_to_add)} nouvelles réceptions ajoutées.")
                    st.rerun()
                else:
                    st.warning("Aucune nouvelle réception détectée.")

        st.subheader("📍 Saisir les emplacements")
        df_need_loc = df_data[(df_data['StatutBL'] == 'A_DEBALLER') & (df_data['Emplacement'] == '')]
        
        if not df_need_loc.empty:
            edited = st.data_editor(
                df_need_loc[['NumReception', 'Magasin', 'Fournisseur', 'Date Livré', 'Emplacement']],
                key="loc_editor", hide_index=True, use_container_width=True
            )
            if st.button("Enregistrer les emplacements"):
                changes = st.session_state["loc_editor"].get("edited_rows", {})
                for idx_str, val in changes.items():
                    rid = df_need_loc.iloc[int(idx_str)]['NumReception']
                    update_multiple_rows([rid], val)
                st.rerun()
        else:
            st.info("Aucun emplacement à saisir.")

    # --- PAGE 2: DEBALLAGE ---
    elif st.session_state.page == '2':
        st.header("2️⃣ Déballage en cours")
        # On affiche ceux qui ont un emplacement et ne sont pas finis
        df_deb = df_data[df_data['StatutBL'].isin(['A_DEBALLER', 'LITIGE']) & (df_data['Emplacement'] != '')]
        
        if df_deb.empty:
            st.info("Rien à déballer pour le moment.")
        else:
            for _, row in df_deb.iterrows():
                with st.expander(f"📦 {row['Fournisseur']} - {row['NumReception']} (Zone: {row['Emplacement']})"):
                    c1, c2 = st.columns(2)
                    with c1:
                        nom = st.text_input("Nom du déballeur", key=f"nom_{row['NumReception']}", value=row['NomDeballage'])
                    with c2:
                        note = st.text_area("Note si litige", key=f"note_{row['NumReception']}", value=row['Commentaire_litige'])
                    
                    b1, b2, _ = st.columns([1,1,2])
                    if b1.button("✅ Terminé", key=f"ok_{row['NumReception']}"):
                        update_multiple_rows([row['NumReception']], {
                            'StatutBL': 'TERMINEE', 'NomDeballage': nom, 
                            'DateDebutDeballage': datetime.now().strftime('%d/%m/%Y')
                        })
                        st.rerun()
                    if b2.button("⚠️ Litige", key=f"ko_{row['NumReception']}"):
                        update_multiple_rows([row['NumReception']], {
                            'StatutBL': 'LITIGE', 'NomDeballage': nom, 'Commentaire_litige': note
                        })
                        st.rerun()

    # --- PAGE TRANSPORT ---
    elif st.session_state.page == 'trans':
        st.header("🚛 Gestion des Transports")
        df_trans = load_data(WS_TRANSPORT, COLUMNS_TRANSPORT)
        
        st.subheader("Créer un nouveau transport")
        next_id = get_next_transport_id(df_trans)
        
        with st.form("form_trans"):
            c1, c2, c3 = st.columns(3)
            tid = c1.text_input("Numéro Transport", value=next_id)
            mag = c2.selectbox("Magasin", ["MAG1", "MAG2", "MAG3"])
            transp = c3.text_input("Transporteur")
            if st.form_submit_button("Générer le transport"):
                new_t = pd.DataFrame([{'NumTransport': tid, 'Magasin': mag, 'NomTransporteur': transp}])
                save_new_rows(WS_TRANSPORT, new_t)
                st.success(f"Transport {tid} créé !")
                st.rerun()

        st.divider()
        st.subheader("Associer des réceptions en rafale")
        df_no_trans = df_data[(df_data['StatutBL'] != 'TERMINEE') & (df_data['NumTransport'] == '')]
        
        if not df_no_trans.empty:
            st.write("Sélectionnez les réceptions à lier au transport :")
            # Ajout d'une colonne de sélection pour le data_editor
            df_no_trans['Sélection'] = False
            sel_cols = ['Sélection', 'NumReception', 'Fournisseur', 'Date Livré', 'Qté']
            
            edited_trans = st.data_editor(
                df_no_trans[sel_cols],
                key="bulk_trans", hide_index=True, use_container_width=True
            )
            
            target_id = st.selectbox("Choisir le numéro de transport cible", options=df_trans['NumTransport'].unique())
            
            if st.button("Lier la sélection au transport"):
                # Récupérer les IDs cochés
                selected_rids = []
                # Le data_editor renvoie les modifs dans edited_rows
                modifs = st.session_state["bulk_trans"].get("edited_rows", {})
                for idx_str, val in modifs.items():
                    if val.get('Sélection'):
                        selected_rids.append(df_no_trans.iloc[int(idx_str)]['NumReception'])
                
                if selected_rids and target_id:
                    update_multiple_rows(selected_rids, {'NumTransport': target_id})
                    st.success(f"{len(selected_rids)} réceptions liées au transport {target_id}")
                    st.rerun()
                else:
                    st.error("Sélectionnez au moins une ligne et un transport.")
        else:
            st.info("Toutes les réceptions actives ont un numéro de transport.")

    # --- PAGE HISTORIQUE ---
    elif st.session_state.page == 'hist':
        st.header("📜 Historique Clôturé")
        st.dataframe(df_data[df_data['StatutBL'] == 'TERMINEE'], use_container_width=True, hide_index=True)

    # --- PAGE LITIGE COMPTA ---
    elif st.session_state.page == 'compta':
        st.header("⚠️ Litiges Comptabilité")
        df_litige = df_data[df_data['StatutBL'] == 'LITIGE']
        st.dataframe(df_litige, use_container_width=True)

if __name__ == "__main__":
    main()
