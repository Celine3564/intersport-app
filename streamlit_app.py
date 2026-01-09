import pandas as pd
import gspread
import streamlit as st
from datetime import datetime

# --- 1. CONFIGURATION ET CONSTANTES ---

SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
WS_TRANSPORT = 'TRANSPORT'
WS_PENDING = 'BL_EN_ATTENTE'

KEY_DATA = 'NumReception'
KEY_TRANS = 'NumTransport'

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

COLUMNS_PENDING = [
    'Fournisseur', 'NumBL', 'DateRecPhysique', 'Statut', 'Montant', 'NbColis','Commentaire'
]

# --- 2. FONCTIONS DE GESTION GOOGLE SHEET ---

def authenticate_gsheet():
    creds = dict(st.secrets['gspread'])
    creds['private_key'] = creds['private_key'].replace('\\n', '\n')
    return gspread.service_account_from_dict(creds)

@st.cache_data(ttl=300)
def load_sheet_data(worksheet_name, columns):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=worksheet_name, rows=100, cols=len(columns))
            ws.append_row(columns)
            return pd.DataFrame(columns=columns)
        
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        return df.reindex(columns=columns).fillna('')
    except Exception as e:
        st.error(f"Erreur lors du chargement de {worksheet_name}: {e}")
        return pd.DataFrame(columns=columns)

def update_gsheet_row(worksheet_name, key_col, key_val, updates):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(worksheet_name)
        headers = ws.row_values(1)
        
        try:
            k_idx = headers.index(key_col) + 1
            cell = ws.find(str(key_val), in_column=k_idx)
        except (ValueError, gspread.exceptions.CellNotFound):
            return False

        batch_updates = []
        for col_name, new_val in updates.items():
            if col_name in headers:
                c_idx = headers.index(col_name) + 1
                batch_updates.append({
                    'range': gspread.utils.rowcol_to_a1(cell.row, c_idx),
                    'values': [[str(new_val)]]
                })
        
        if batch_updates:
            ws.batch_update(batch_updates)
            st.cache_data.clear()
            return True
    except Exception as e:
        st.error(f"Erreur update: {e}")
        return False

def append_to_sheet(worksheet_name, df_to_add):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(worksheet_name)
        ws.append_rows(df_to_add.values.tolist(), value_input_option='USER_ENTERED')
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur ajout: {e}")
        return False

# --- 3. LOGIQUE MÉTIER ---

def import_nozymag(uploaded_file):
    df_new = pd.read_excel(uploaded_file)
    df_new.columns = df_new.columns.str.strip()
    
    # GESTION DU NOM DE COLONNE FLEXIBLE
    # On vérifie si 'NumeroAuto' existe, si oui on le renomme en 'NumRéception'
    if 'NumeroAuto' in df_new.columns and 'NumReception' not in df_new.columns:
        df_new = df_new.rename(columns={'NumeroAuto': 'NumReception'})
        st.info("Mapping : 'NumeroAuto' utilisé comme 'NumReception'")

    # Validation minimale
    required = ['NumRéception', 'Magasin', 'Fournisseur']
    if not all(c in df_new.columns for c in required):
        st.error(f"Colonnes manquantes. Besoin de : {required} ou 'NumeroAuto'")
        return

    df_existing = load_sheet_data(WS_DATA, COLUMNS_DATA)
    existing_ids = set(df_existing[KEY_DATA].astype(str))
    
    # Filtrer les doublons
    df_to_add = df_new[~df_new['NumRéception'].astype(str).isin(existing_ids)].copy()
    
    if not df_to_add.empty:
        df_to_add['StatutBL'] = 'A_DEBALLER'
        # Remplir les colonnes manquantes pour correspondre au Google Sheet
        for col in COLUMNS_DATA:
            if col not in df_to_add.columns:
                df_to_add[col] = ''
        
        df_to_add = df_to_add[COLUMNS_DATA].astype(str)
        if append_to_sheet(WS_DATA, df_to_add):
            st.success(f"{len(df_to_add)} nouvelles réceptions ajoutées.")
            st.rerun()
    else:
        st.warning("Toutes les lignes de ce fichier existent déjà dans la base.")

# --- 4. INTERFACE UTILISATEUR ---

def main():
    st.set_page_config(page_title="NozyLogistique", layout="wide")
    
    if 'page' not in st.session_state: st.session_state.page = 'accueil'

    with st.sidebar:
        st.title("📦 Suivi Logistique Groupe Dumasdelage")
        if st.button("🏠 Accueil", use_container_width=True): st.session_state.page = 'accueil'
        st.divider()
        st.write("**FLUX DE TRAVAIL**")
        if st.button("1️⃣ Import Réception et Stockage Emplacement", use_container_width=True): st.session_state.page = 'p1'
        if st.button("2️⃣ Transporteurs", use_container_width=True): st.session_state.page = 'p2'
        if st.button("3️⃣ Déballage & Litiges", use_container_width=True): st.session_state.page = 'p3'
        if st.button("4️⃣ Historique Clôturé", use_container_width=True): st.session_state.page = 'p4'
        st.divider()
        if st.button("📋 BL en attente", use_container_width=True): st.session_state.page = 'pending'

    df_data = load_sheet_data(WS_DATA, COLUMNS_DATA)

    # --- PAGES ---

    if st.session_state.page == 'accueil':
        st.title("Tableau de bord")
        c1, c2, c3 = st.columns(3)
        c1.metric("A Déballer", len(df_data[df_data['StatutBL'] == 'A_DEBALLER']))
        c2.metric("En Litige", len(df_data[df_data['StatutBL'] == 'LITIGE']))
        c3.metric("Terminées", len(df_data[df_data['StatutBL'] == 'TERMINEE']))

    elif st.session_state.page == 'p1':
        st.header("1️⃣ Import Nozymag & Emplacements")
        
        with st.expander("📥 Importer fichier Nozymag"):
            st.write("Le système accepte les colonnes 'NumRéception' ou 'NumeroAuto'.")
            up = st.file_uploader("Fichier Excel", type=['xlsx'])
            if up and st.button("Lancer l'import"): import_nozymag(up)

        st.subheader("Saisie des emplacements (Statut: A Déballer)")
        df_p1 = df_data[df_data['StatutBL'] == 'A_DEBALLER'].copy()
        
        if df_p1.empty:
            st.info("Aucune réception en attente d'emplacement.")
        else:
            edited = st.data_editor(
                df_p1,
                column_order=['NumRéception', 'Magasin', 'Fournisseur', 'Emplacement'],
                disabled=['NumRéception', 'Magasin', 'Fournisseur'],
                key="p1_editor",
                use_container_width=True,
                hide_index=True
            )
            
            if st.button("Enregistrer les emplacements"):
                changes = st.session_state["p1_editor"].get("edited_rows", {})
                for idx, val in changes.items():
                    rid = df_p1.iloc[int(idx)][KEY_DATA]
                    update_gsheet_row(WS_DATA, KEY_DATA, rid, val)
                st.success("Mise à jour réussie.")
                st.rerun()

    elif st.session_state.page == 'p2':
        st.header("2️⃣ Gestion des Transports")
        df_trans = load_sheet_data(WS_TRANSPORT, COLUMNS_TRANSPORT)
        
        with st.expander("➕ Enregistrer un nouveau transporteur"):
            with st.form("new_trans"):
                nt = st.text_input("Numéro de Transport (ID unique)")
                tr_name = st.text_input("Nom Transporteur")
                nb_p = st.number_input("Nombre Palettes", 0)
                if st.form_submit_button("Valider"):
                    if nt:
                        append_to_sheet(WS_TRANSPORT, pd.DataFrame([{'NumTransport': nt, 'NomTransporteur': tr_name, 'NbPalettes': nb_p}]))
                        st.success("Transport enregistré.")
                    else: st.error("Le Numéro de Transport est obligatoire.")

        st.subheader("Associer Transport à Réception")
        col_rec, col_tr = st.columns(2)
        with col_rec:
            sel_rec = st.selectbox("Réception", df_data[df_data['StatutBL'] != 'TERMINEE'][KEY_DATA])
        with col_tr:
            sel_tr = st.selectbox("Transporteur", [""] + list(df_trans[KEY_TRANS].unique()))
        
        if st.button("Lier"):
            update_gsheet_row(WS_DATA, KEY_DATA, sel_rec, {'NumTransport': sel_tr})
            st.success("Lien mis à jour.")

    elif st.session_state.page == 'p3':
        st.header("3️⃣ Déballage en cours")
        df_deballe = df_data[df_data['StatutBL'].isin(['A_DEBALLER', 'LITIGE'])].copy()

        if df_deballe.empty:
            st.info("Rien à déballer pour le moment.")
        else:
            for _, row in df_deballe.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 2])
                    c1.markdown(f"**Réception: {row[KEY_DATA]}**\n\n{row['Fournisseur']} | Emplacement: `{row['Emplacement']}`")
                    
                    with c2:
                        name = st.text_input("Déballeur", value=row['NomDeballage'], key=f"n_{row[KEY_DATA]}")
                        com = st.text_area("Com. Litige", value=row['Commentaire_litige'], key=f"c_{row[KEY_DATA]}", height=68)
                    
                    with c3:
                        st.write(f"Statut: **{row['StatutBL']}**")
                        if st.button("✅ Terminer", key=f"t_{row[KEY_DATA]}"):
                            update_gsheet_row(WS_DATA, KEY_DATA, row[KEY_DATA], {
                                'NomDeballage': name, 'StatutBL': 'TERMINEE',
                                'DateDebutDeballage': datetime.now().strftime('%d/%m/%Y %H:%M')
                            })
                            st.rerun()
                        if st.button("⚠️ Litige", key=f"l_{row[KEY_DATA]}"):
                            update_gsheet_row(WS_DATA, KEY_DATA, row[KEY_DATA], {
                                'NomDeballage': name, 'StatutBL': 'LITIGE', 'Commentaire_litige': com
                            })
                            st.rerun()

    elif st.session_state.page == 'p4':
        st.header("4️⃣ Réceptions Clôturées")
        st.dataframe(df_data[df_data['StatutBL'] == 'TERMINEE'], use_container_width=True, hide_index=True)

    elif st.session_state.page == 'pending':
        st.header("📋 BL en attente de saisie")
        df_p = load_sheet_data(WS_PENDING, COLUMNS_PENDING)
        st.table(df_p)

if __name__ == "__main__":
    main()
