import pandas as pd
import gspread
import streamlit as st
from datetime import datetime

# --- 1. CONFIGURATION ET CONSTANTES ---

SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
WS_TRANSPORT = 'TRANSPORT'
WS_PENDING = 'BL_EN_ATTENTE'

# Clé Primaire
KEY_DATA = 'NumRéception'
KEY_TRANS = 'NumTransport'

# Définition des colonnes selon vos spécifications
COLUMNS_DATA = [
    'NumRéception', 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Date Livré', 'Qté', 'Collection', 'Num Facture', 'StatutBL', 
    'Emplacement', 'NomDeballage', 'DateDebutDeballage', 'LitigesCompta', 
    'Commentaire_litige', 'NumTransport'
]

COLUMNS_TRANSPORT = [
    'NumTransport', 'Magasin', 'NomTransporteur', 'NbPalettes', 
    'Poids_total', 'Commentaire_Livraison', 'Colis_manquant/abimé/ouvert', 'LitigeReception'
]

COLUMNS_PENDING = [
    'Fournisseur', 'NuméroBL', 'DateReceptionPhysique', 'Statut', 'Montant', 'NbColis'
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
    """Met à jour une ligne spécifique basée sur une clé unique."""
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(worksheet_name)
        headers = ws.row_values(1)
        
        # Trouver la colonne de la clé
        try:
            k_idx = headers.index(key_col) + 1
            cell = ws.find(str(key_val), in_column=k_idx)
        except (ValueError, gspread.exceptions.CellNotFound):
            st.error(f"Entrée {key_val} introuvable dans {worksheet_name}")
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
    
    # Validation minimale des colonnes requises
    required = ['NumRéception', 'Magasin', 'Fournisseur', 'Mt TTC']
    if not all(c in df_new.columns for c in required):
        st.error("Colonnes manquantes dans l'Excel.")
        return

    # Préparation des données
    df_existing = load_sheet_data(WS_DATA, COLUMNS_DATA)
    existing_ids = set(df_existing[KEY_DATA].astype(str))
    
    df_to_add = df_new[~df_new['NumRéception'].astype(str).isin(existing_ids)].copy()
    
    if not df_to_add.empty:
        # Valeurs par défaut
        df_to_add['StatutBL'] = 'A_DEBALLER'
        for col in COLUMNS_DATA:
            if col not in df_to_add.columns:
                df_to_add[col] = ''
        
        df_to_add = df_to_add[COLUMNS_DATA].astype(str)
        if append_to_sheet(WS_DATA, df_to_add):
            st.success(f"{len(df_to_add)} réceptions importées avec statut 'A_DEBALLER'.")
            st.rerun()
    else:
        st.warning("Aucune nouvelle réception à importer.")

# --- 4. INTERFACE UTILISATEUR ---

def main():
    st.set_page_config(page_title="NozyLogistique", layout="wide")
    
    if 'page' not in st.session_state: st.session_state.page = 'accueil'

    # Sidebar Navigation
    with st.sidebar:
        st.title("📦 NozyLog")
        if st.button("🏠 Accueil", use_container_width=True): st.session_state.page = 'accueil'
        st.divider()
        if st.button("1️⃣ Import & Emplacement", use_container_width=True): st.session_state.page = 'p1'
        if st.button("2️⃣ Transporteurs", use_container_width=True): st.session_state.page = 'p2'
        if st.button("3️⃣ Déballage & Litiges", use_container_width=True): st.session_state.page = 'p3'
        if st.button("4️⃣ Historique Clôturé", use_container_width=True): st.session_state.page = 'p4'
        if st.button("📋 BL en attente", use_container_width=True): st.session_state.page = 'pending'

    df_data = load_sheet_data(WS_DATA, COLUMNS_DATA)

    # --- ROUTAGE DES PAGES ---

    if st.session_state.page == 'accueil':
        st.title("Tableau de bord Logistique")
        st.write("Bienvenue dans le système de gestion des réceptions.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("A Déballer", len(df_data[df_data['StatutBL'] == 'A_DEBALLER']))
        c2.metric("En Litige", len(df_data[df_data['StatutBL'] == 'LITIGE']))
        c3.metric("Terminées", len(df_data[df_data['StatutBL'] == 'TERMINEE']))

    elif st.session_state.page == 'p1':
        st.header("1️⃣ Import des réceptions & Emplacements")
        
        with st.expander("📥 Importer Nozymag"):
            up = st.file_uploader("Fichier Excel", type=['xlsx'])
            if up and st.button("Lancer l'import"): import_nozymag(up)

        st.subheader("Liste des réceptions à traiter")
        # Filtrer uniquement les lignes sans emplacement ou statut initial
        df_p1 = df_data[df_data['StatutBL'] == 'A_DEBALLER'].copy()
        
        edited = st.data_editor(
            df_p1,
            column_order=['NumRéception', 'Magasin', 'Fournisseur', 'Date Livré', 'Emplacement'],
            disabled=['NumRéception', 'Magasin', 'Fournisseur', 'Date Livré'],
            key="p1_editor",
            use_container_width=True,
            hide_index=True
        )
        
        if st.button("Enregistrer les emplacements"):
            changes = st.session_state["p1_editor"].get("edited_rows", {})
            for idx, val in changes.items():
                rid = df_p1.iloc[int(idx)][KEY_DATA]
                update_gsheet_row(WS_DATA, KEY_DATA, rid, val)
            st.success("Emplacements mis à jour.")
            st.rerun()

    elif st.session_state.page == 'p2':
        st.header("2️⃣ Associer un Transporteur (Facultatif)")
        
        # Formulaire création transport
        with st.expander("➕ Créer un nouveau transport"):
            with st.form("trans_form"):
                nt = st.text_input("NumTransport (Clé)")
                mag = st.selectbox("Magasin", sorted(df_data['Magasin'].unique()))
                tr_name = st.text_input("Nom Transporteur")
                pal = st.number_input("Nombre Palettes", min_value=0)
                if st.form_submit_button("Créer Transport"):
                    new_t = pd.DataFrame([{
                        'NumTransport': nt, 'Magasin': mag, 'NomTransporteur': tr_name, 'NbPalettes': pal
                    }])
                    append_to_sheet(WS_TRANSPORT, new_t)
                    st.success("Transport créé.")

        st.subheader("Associer Transport à Réception")
        df_trans = load_sheet_data(WS_TRANSPORT, COLUMNS_TRANSPORT)
        
        # Filtrage
        target_rec = st.selectbox("Sélectionner la Réception", df_data[df_data['StatutBL'] != 'TERMINEE'][KEY_DATA])
        target_trans = st.selectbox("Sélectionner le Transport", ["Aucun"] + list(df_trans[KEY_TRANS].unique()))
        
        if st.button("Lier le transport"):
            update_gsheet_row(WS_DATA, KEY_DATA, target_rec, {'NumTransport': target_trans if target_trans != "Aucun" else ''})
            st.success("Lien effectué.")

    elif st.session_state.page == 'p3':
        st.header("3️⃣ Liste des Réceptions à Déballer")
        df_deballe = df_data[df_data['StatutBL'].isin(['A_DEBALLER', 'LITIGE'])].copy()

        if df_deballe.empty:
            st.info("Aucune réception à déballer.")
        else:
            # On affiche les lignes
            for index, row in df_deballe.iterrows():
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                    c1.write(f"**{row['NumRéception']}** - {row['Fournisseur']}")
                    c2.write(f"Emplacement: {row['Emplacement']}")
                    c3.write(f"Statut actuel: {row['StatutBL']}")
                    
                    with st.expander("Action Déballage"):
                        name = st.text_input("Nom du déballeur", value=row['NomDeballage'], key=f"n_{row[KEY_DATA]}")
                        com = st.text_area("Commentaire / Litige", value=row['Commentaire_litige'], key=f"c_{row[KEY_DATA]}")
                        
                        btn_col1, btn_col2 = st.columns(2)
                        if btn_col1.button("✅ Terminer", key=f"t_{row[KEY_DATA]}"):
                            update_gsheet_row(WS_DATA, KEY_DATA, row[KEY_DATA], {
                                'NomDeballage': name,
                                'StatutBL': 'TERMINEE',
                                'DateDebutDeballage': datetime.now().strftime('%Y-%m-%d %H:%M')
                            })
                            st.rerun()
                        
                        if btn_col2.button("⚠️ Ouvrir Litige", key=f"l_{row[KEY_DATA]}", type="secondary"):
                            update_gsheet_row(WS_DATA, KEY_DATA, row[KEY_DATA], {
                                'NomDeballage': name,
                                'StatutBL': 'LITIGE',
                                'Commentaire_litige': com
                            })
                            st.rerun()

    elif st.session_state.page == 'p4':
        st.header("4️⃣ Historique des Réceptions Clôturées")
        df_cloture = df_data[df_data['StatutBL'] == 'TERMINEE']
        st.dataframe(df_cloture, use_container_width=True, hide_index=True)

    elif st.session_state.page == 'pending':
        st.header("📋 Marchandise en attente (Non saisie)")
        df_p = load_sheet_data(WS_PENDING, COLUMNS_PENDING)
        
        with st.expander("Ajouter un BL physique"):
            with st.form("pending_form"):
                f = st.text_input("Fournisseur")
                bl = st.text_input("Numéro BL")
                mt = st.number_input("Montant", min_value=0.0)
                if st.form_submit_button("Ajouter à l'attente"):
                    new_p = pd.DataFrame([{
                        'Fournisseur': f, 'NuméroBL': bl, 'Montant': mt, 
                        'DateReceptionPhysique': datetime.now().strftime('%Y-%m-%d'),
                        'Statut': 'Attente Saisie'
                    }])
                    append_to_sheet(WS_PENDING, new_p)
                    st.rerun()
        
        st.table(df_p)

if __name__ == "__main__":
    main()
