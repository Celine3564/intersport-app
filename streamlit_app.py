import pandas as pd
import gspread
import streamlit as st
from datetime import datetime

# --- CONFIGURATION ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
COLUMNS_DATA = [
    'NumReception', 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Livré le', 'Qté', 'Collection', 'Num Facture', 'StatutBL', 
    'Emplacement', 'NomDeballage', 'Date Clôture', 'LitigesCompta', 
    'Commentaire_litige', 'NumTransport'
]

# --- FONCTIONS DE FORMATAGE ---
def format_currency(val):
    try:
        if not val or str(val).strip() == "": return "0,00 €"
        num = float(str(val).replace(',', '.').replace('€', '').replace(' ', ''))
        return f"{num:,.2f} €".replace(',', ' ').replace('.', ',')
    except:
        return val

def format_number(val):
    try:
        if not val or str(val).strip() == "": return "0"
        num = int(float(str(val).replace(' ', '')))
        return f"{num:,}".replace(',', ' ')
    except:
        return val

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
        # Harmonisation des noms de colonnes si nécessaire
        if 'Date Livré' in df.columns: df = df.rename(columns={'Date Livré': 'Livré le'})
        if 'NumReception' in df.columns: df['NumReception'] = df['NumReception'].astype(str)
        return df.reindex(columns=cols).fillna('')
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
        return pd.DataFrame(columns=cols)

def update_single_row(reception_id, updates):
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_DATA)
        headers = ws.row_values(1)
        cell = ws.find(str(reception_id), in_column=1)
        if cell:
            for col_name, val in updates.items():
                if col_name in headers:
                    c_idx = headers.index(col_name) + 1
                    ws.update_cell(cell.row, c_idx, str(val))
            return True
        return False
    except Exception as e:
        st.error(f"Erreur d'écriture : {e}")
        return False

# --- INTERFACE PRINCIPALE ---
def main():
    st.set_page_config(page_title="NozyLog", layout="wide")
    
    if 'page' not in st.session_state: st.session_state.page = '1'

    # Barre latérale de navigation
    with st.sidebar:
        st.title("📦 NozyLog")
        if st.button("1️⃣ Import Fichier"): st.session_state.page = '1'
        if st.button("2️⃣ Emplacement"): st.session_state.page = '2'
        if st.button("3️⃣ Déballage"): st.session_state.page = '3'
        st.divider()
        if st.button("🚛 Transport"): st.session_state.page = 'trans'
        if st.button("📜 Historique"): st.session_state.page = 'hist'
        if st.button("⚠️ Litiges"): st.session_state.page = 'compta'

    # Chargement global des données
    df_all = load_data(WS_DATA, COLUMNS_DATA)

    # Pré-formatage pour l'affichage (sans modifier les IDs de liaison)
    df_display = df_all.copy()
    if not df_display.empty:
        df_display['Mt TTC'] = df_display['Mt TTC'].apply(format_currency)
        df_display['Qté'] = df_display['Qté'].apply(format_number)

    # --- PAGE 1 : IMPORTATION ---
    if st.session_state.page == '1':
        st.header("1️⃣ Importation des Réceptions")
        st.write("Téléchargez ici votre fichier Excel Nozymag pour mettre à jour la base de données.")
        
        uploaded_file = st.file_uploader("Choisir un fichier Excel (.xlsx)", type="xlsx")
        
        if uploaded_file:
            try:
                df_new = pd.read_excel(uploaded_file)
                st.success("Fichier chargé avec succès !")
                st.dataframe(df_new.head(), use_container_width=True)
                
                if st.button("🚀 Lancer la synchronisation"):
                    with st.spinner("Fusion des données en cours..."):
                        # Ici vous pouvez appeler votre logique de fusion import_excel.py
                        st.info("Logique d'importation activée. Les nouvelles lignes seront ajoutées à la feuille Google.")
            except Exception as e:
                st.error(f"Erreur lors de la lecture du fichier : {e}")

    # --- PAGE 2 : EMPLACEMENT ---
    elif st.session_state.page == '2':
        st.header("2️⃣ Saisie d'emplacement")
        search_query = st.text_input("🔍 Rechercher une réception :", "").lower()
        
        # Filtrage : Uniquement ce qui est "À déballer" et SANS emplacement
        df_no_loc = df_display[
            (df_display['StatutBL'] == 'À déballer') & 
            (df_display['Emplacement'].astype(str).str.strip() == '')
        ].copy()
        
        if search_query:
            df_no_loc = df_no_loc[df_no_loc.apply(lambda row: search_query in row.astype(str).str.lower().values, axis=1)]

        if df_no_loc.empty:
            st.success("Toutes les réceptions ont un emplacement affecté.")
        else:
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
                if not changes:
                    st.warning("Aucune modification détectée.")
                else:
                    for idx_str, val in changes.items():
                        rid = df_no_loc.iloc[int(idx_str)]['NumReception']
                        update_single_row(rid, val)
                    st.success("Emplacements mis à jour !")
                    st.rerun()

    # --- PAGE 3 : DEBALLAGE ---
    elif st.session_state.page == '3':
        st.header("3️⃣ Déballage et Contrôle")
        search_query = st.text_input("🔍 Rechercher (Emplacement, Fournisseur...) :", "").lower()
        
        # Filtrage : En cours (À déballer/Litige) ET avec un emplacement
        df_work = df_display[
            (df_display['StatutBL'].isin(['À déballer', 'LITIGE'])) & 
            (df_display['Emplacement'].astype(str).str.strip() != '')
        ].copy()
        
        if search_query:
            df_work = df_work[df_work.apply(lambda row: search_query in row.astype(str).str.lower().values, axis=1)]
        
        if df_work.empty:
            st.info("Aucun déballage en attente avec emplacement.")
        else:
            df_work['✅ Terminer'] = False
            df_work['⚠️ Litige'] = False
            cols_display = ['NumReception', 'Fournisseur', 'Emplacement', 'N° Fourn.', 'Mt TTC', 'Livré le', 'Qté', 'NomDeballage', 'Commentaire_litige', '✅ Terminer', '⚠️ Litige']
            
            edited_deb = st.data_editor(
                df_work[cols_display],
                key="deb_editor",
                hide_index=True,
                use_container_width=True,
                disabled=['NumReception', 'Fournisseur', 'Emplacement', 'N° Fourn.', 'Mt TTC', 'Livré le', 'Qté']
            )
            
            if st.button("🚀 Valider les déballages"):
                changes = st.session_state["deb_editor"].get("edited_rows", {})
                for idx_str, val in changes.items():
                    rid = df_work.iloc[int(idx_str)]['NumReception']
                    update_data = {}
                    
                    if val.get('✅ Terminer'):
                        update_data = {'StatutBL': 'Clôturée', 'Date Clôture': datetime.now().strftime('%d/%m/%Y')}
                    elif val.get('⚠️ Litige'):
                        update_data = {'StatutBL': 'LITIGE'}
                    
                    if 'NomDeballage' in val: update_data['NomDeballage'] = val['NomDeballage']
                    if 'Commentaire_litige' in val: update_data['Commentaire_litige'] = val['Commentaire_litige']
                    
                    if update_data: update_single_row(rid, update_data)
                st.success("Mise à jour effectuée !")
                st.rerun()

    # --- PAGES ANNEXES ---
    elif st.session_state.page == 'hist':
        st.header("📜 Historique des réceptions clôturées")
        st.dataframe(df_display[df_display['StatutBL'] == 'Clôturée'], use_container_width=True, hide_index=True)

    elif st.session_state.page == 'compta':
        st.header("⚠️ Gestion des Litiges")
        st.dataframe(df_display[df_display['StatutBL'] == 'LITIGE'], use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
