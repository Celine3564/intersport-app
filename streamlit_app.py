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
def format_currency_custom(val):
    """Transforme 5653,46 en 5 653€ (Arrondi entier avec espace milliers)"""
    try:
        if not val or str(val).strip() == "": return "0€"
        num_str = str(val).replace(',', '.').replace('€', '').replace(' ', '')
        num = float(num_str)
        rounded_num = int(round(num))
        formatted = f"{rounded_num:,}".replace(',', ' ')
        return f"{formatted}€"
    except:
        return val

def format_number(val):
    """Formatage des quantités avec espace milliers"""
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

    # Barre latérale
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

    # Application du formatage visuel pour l'affichage
    df_display = df_all.copy()
    if not df_display.empty:
        df_display['Mt TTC'] = df_display['Mt TTC'].apply(format_currency_custom)
        df_display['Qté'] = df_display['Qté'].apply(format_number)

    # --- PAGE 1 : IMPORTATION ---
    if st.session_state.page == '1':
        st.header("1️⃣ Importation des Réceptions")
        st.info("Module de synchronisation Nozymag")
        uploaded_file = st.file_uploader("Fichier Excel Nozymag (.xlsx)", type="xlsx")
        
        if uploaded_file:
            df_new = pd.read_excel(uploaded_file)
            st.success("Fichier prêt pour l'analyse")
            st.dataframe(df_new.head(), use_container_width=True)
            if st.button("🚀 Lancer l'importation"):
                st.warning("Action : Les données vont être fusionnées avec Google Sheets.")

    # --- PAGE 2 : EMPLACEMENT ---
    elif st.session_state.page == '2':
        st.header("2️⃣ Saisie d'emplacement")
        search = st.text_input("🔍 Recherche (Fournisseur, N°, Facture, Statut...) :", "").lower()
        
        # Filtre : Statut "À déballer" et Emplacement vide
        df_filtered = df_display[
            (df_display['StatutBL'] == 'À déballer') & 
            (df_display['Emplacement'].astype(str).str.strip() == '')
        ].copy()
        
        if search:
            mask = df_filtered.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
            df_filtered = df_filtered[mask]

        if df_filtered.empty:
            st.info("Aucune réception en attente d'emplacement (déjà rangée ou clôturée).")
        else:
            cols_edit = ['NumReception', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 'Livré le', 'Qté', 'Emplacement']
            edited = st.data_editor(
                df_filtered[cols_edit],
                key="loc_editor", 
                hide_index=True, 
                use_container_width=True,
                disabled=['NumReception', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 'Livré le', 'Qté']
            )
            
            if st.button("💾 Valider les emplacements"):
                rows = st.session_state["loc_editor"].get("edited_rows", {})
                for idx, val in rows.items():
                    rid = df_filtered.iloc[int(idx)]['NumReception']
                    update_single_row(rid, val)
                st.success("Mise à jour effectuée")
                st.rerun()

    # --- PAGE 3 : DEBALLAGE ---
    elif st.session_state.page == '3':
        st.header("3️⃣ Déballage et Contrôle")
        st.subheader("Liste de toutes les réceptions à déballer")
        search = st.text_input("🔍 Recherche globale (Emplacement, Fournisseur, N°...) :", "").lower()
        
        # NOUVEAU FILTRE : Toutes les réceptions "À déballer" ou "LITIGE", peu importe l'emplacement
        df_work = df_display[
            df_display['StatutBL'].isin(['À déballer', 'LITIGE'])
        ].copy()
        
        if search:
            mask = df_work.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
            df_work = df_work[mask]
        
        if df_work.empty:
            st.info("Aucun article en attente de déballage.")
        else:
            # Ajout de colonnes temporaires pour l'action utilisateur
            df_work['✅ OK'] = False
            df_work['⚠️ Litige'] = False
            
            cols_show = [
                'NumReception', 'Fournisseur', 'Emplacement', 'N° Fourn.', 
                'Mt TTC', 'Livré le', 'Qté', 'NomDeballage', 
                'Commentaire_litige', '✅ OK', '⚠️ Litige'
            ]
            
            edited_deb = st.data_editor(
                df_work[cols_show],
                key="deb_editor",
                hide_index=True,
                use_container_width=True,
                disabled=['NumReception', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 'Livré le', 'Qté']
            )
            
            if st.button("🚀 Enregistrer le pointage"):
                rows = st.session_state["deb_editor"].get("edited_rows", {})
                if not rows:
                    st.warning("Aucune modification détectée.")
                else:
                    for idx, val in rows.items():
                        rid = df_work.iloc[int(idx)]['NumReception']
                        upd = {}
                        if val.get('✅ OK'):
                            upd = {'StatutBL': 'Clôturée', 'Date Clôture': datetime.now().strftime('%d/%m/%Y')}
                        elif val.get('⚠️ Litige'):
                            upd = {'StatutBL': 'LITIGE'}
                        
                        # On récupère les autres champs s'ils ont été modifiés
                        if 'NomDeballage' in val: upd['NomDeballage'] = val['NomDeballage']
                        if 'Commentaire_litige' in val: upd['Commentaire_litige'] = val['Commentaire_litige']
                        if 'Emplacement' in val: upd['Emplacement'] = val['Emplacement']
                        
                        if upd: update_single_row(rid, upd)
                    st.success("Pointage enregistré avec succès.")
                    st.rerun()

    # --- HISTORIQUE ---
    elif st.session_state.page == 'hist':
        st.header("📜 Historique des réceptions clôturées")
        search_hist = st.text_input("🔍 Rechercher dans l'historique :", "").lower()
        df_hist = df_display[df_display['StatutBL'] == 'Clôturée']
        
        if search_hist:
            mask = df_hist.apply(lambda row: row.astype(str).str.contains(search_hist, case=False, na=False).any(), axis=1)
            df_hist = df_hist[mask]
            
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
