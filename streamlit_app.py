import pandas as pd
import gspread
import streamlit as st
from datetime import datetime
import requests
import smtplib
import re
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# --- CONFIGURATION & CONSTANTES ---
SHEET_ID = '1JT_Lq_TvPL2lQc2ArPBi48bVKdSgU2m_SyPFHSQsGtk'
WS_DATA = 'DATA'
WS_REFUS = 'REFUS'
WS_MAILS = 'MAIL' # Onglet contenant la liste des destinataires
WS_TRANSPORT = 'TRANSPORT'
apiKey = "" # La clé API est injectée automatiquement par l'environnement

# ONGLET DATA
COLUMNS_DATA = [
    'NumReception', 'Magasin', 'Fournisseur', 'N° Fourn.', 'Mt TTC', 
    'Livré le', 'Qté', 'Collection', 'Num Facture', 'StatutBL', 
    'Emplacement', 'NomDeballage', 'DateClotureDeballage', 'LitigesCompta', 
    'Commentaire_litige', 'NumTransport'
]
# Colonnes basées l'onglet REFUS
COLUMNS_REFUS = ['MAGASIN', 'Date du refus', 'Nom du fournisseur', 'Num du BL','Commentaire du refus']
# Colonnes basées l'onglet TRANSPPORT			
COLUMNS_TRANSPORT = [
    'NumTransport', 'Magasin', 'NomTransporteur', 'NbPalettes', 
    'Poids_total', 'Commentaire_Livraison', 'Colis_abime_ouvert', 'LitigeReception'
]

# --- FONCTIONS TECHNIQUES ---
def authenticate_gsheet():
    try:
        if 'gspread' not in st.secrets:
            st.error("❌ Les secrets 'gspread' ne sont pas configurés dans Streamlit Cloud.")
            return None
        creds = dict(st.secrets['gspread'])
        creds['private_key'] = creds['private_key'].replace('\\n', '\n')
        return gspread.service_account_from_dict(creds)
    except Exception as e:
        st.error(f"❌ Erreur d'authentification : {e}")
        return None

def load_data(ws_name, cols):
    """Charge les données d'un onglet en ignorant les colonnes vides dupliquées."""
    try:
        gc = authenticate_gsheet()
        if not gc: return pd.DataFrame(columns=cols)
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(ws_name)
        
        # On récupère toutes les valeurs pour filtrer les colonnes vides qui causent l'erreur 'duplicates'
        all_values = ws.get_all_values()
        if not all_values:
            return pd.DataFrame(columns=cols)
            
        header = all_values[0]
        data = all_values[1:]
        df = pd.DataFrame(data, columns=header)
        
        # Supprimer les colonnes sans nom (vides) qui font planter AgGrid/Pandas
        df = df.loc[:, ~df.columns.duplicated()]
        if '' in df.columns:
            df = df.drop(columns=[''])
            
        # Nettoyage des noms de colonnes
        df.columns = [c.strip() for c in df.columns]
        
        # S'assurer que toutes les colonnes attendues sont présentes
        for col in cols:
            if col not in df.columns:
                df[col] = ""
                
        return df[cols].fillna('').iloc[::-1]
    except Exception as e:
        # Fallback si get_all_records échoue à cause des doublons
        return pd.DataFrame(columns=cols)


def save_data_to_gsheet(df_updated):
    """Sauvegarde complète de la feuille (plus fiable que update_cell par cell)"""
    try:
        gc = authenticate_gsheet()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_DATA)
        
        # Préparation des données (headers + data)
        # Conversion des dates/objets en string pour JSON
        df_to_save = df_updated.copy()
        for col in df_to_save.columns:
            df_to_save[col] = df_to_save[col].astype(str).replace(['NaT', 'nan', 'None'], '')
            
        data_to_upload = [df_to_save.columns.values.tolist()] + df_to_save.values.tolist()
        
        ws.update('A1', data_to_upload)
        return True
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")
        return False

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Refus')
    return output.getvalue()

def add_row_gsheet(ws_name, row_list):
    try:
        gc = authenticate_gsheet()
        if not gc: return False
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(ws_name)
        ws.append_row(row_list)
        return True
    except Exception as e:
        st.error(f"❌ Erreur GSheet : {e}")
        return False
		
#DEF TABLEAU MISE EN PAGE
def get_standard_grid_options(df, page_size=20, editable_cols=[]):
    """
    FONCTION CENTRALISÉE : Configure tous les tableaux AgGrid du site.
    Active la saisie libre, le filtrage et les options d'export.
    """
    gb = GridOptionsBuilder.from_dataframe(df)
    
    # Configuration par défaut
    gb.configure_default_column(
        resizable=True, 
        sortable=True, 
        filter='agTextColumnFilter',
        floatingFilter=True,
        minWidth=100,
        editable=False
    )
    
    # Activation de l'exportation CSV (similaire à l'option "Extraire" de Streamlit)
    gb.configure_grid_options(enableExport=True)
    
    # Configuration des colonnes spécifiques
    if 'Date du refus' in df.columns:
        gb.configure_column('Date du refus', filter='agDateColumnFilter')
    
    for col in editable_cols:
        if col in df.columns:
            gb.configure_column(col, editable=True, cellStyle={'background-color': '#f0f7ff'})
    
    # Pagination
    gb.configure_pagination(
        enabled=True, 
        paginationAutoPageSize=False, 
        paginationPageSize=page_size
    )
    
    # Permet la sélection multiple pour l'extraction
    gb.configure_selection(selection_mode="multiple", use_checkbox=True)
    
    return gb.build()

#DEF FEUILLE REFUS
def add_refus_row(row_list):
    """Ajoute réellement la ligne dans l'onglet REFUS"""
    try:
        gc = authenticate_gsheet()
        if not gc: return False
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_REFUS)
        ws.append_row(row_list)
        return True
    except Exception as e:
        st.error(f"❌ Erreur lors de l'écriture dans Google Sheets : {e}")
        return False

def send_actual_email(destinataires_list, subject, body, attachment=None):
    """
    Envoie un e-mail réel.
    destinataires_list : Liste Python d'adresses e-mails propres.
    """
    try:
        if "email" not in st.secrets: 
            return False, "Configuration e-mail manquante."
        
        config = st.secrets["email"]
        sender = extreme_clean(config["sender_email"])
        
        # Nettoyage de la liste des destinataires
        clean_dests = [extreme_clean(m) for m in destinataires_list if "@" in str(m)]
        if not clean_dests:
            return False, "Aucun destinataire valide."

        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = ", ".join(clean_dests)
        msg['Subject'] = Header(subject, 'utf-8').encode()
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        if attachment is not None:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{attachment.name}"')
            msg.attach(part)
            
        server = smtplib.SMTP(extreme_clean(config["smtp_server"]), int(config["smtp_port"]))
        server.starttls()
        server.login(sender, extreme_clean(config["sender_password"]))
        # On passe la liste Python directement
        server.sendmail(sender, clean_dests, msg.as_string())
        server.quit()
        return True, "Succès"
    except Exception as e:
        return False, str(e)

def generate_mail_content(magasin, fournisseur, bl, commentaire):
    prompt = f"Rédige un mail pro court: Refus de marchandise. Magasin {magasin}, Fournisseur {fournisseur}, BL {bl}. Motif: {commentaire}."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={apiKey}"
    try:
        response = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except:
        return f"Refus du BL {bl} ({fournisseur}) au magasin {magasin}.\nMotif : {commentaire}"
		
def generate_ai_content(magasin, fournisseur, bl, commentaire):
    """Génère le corps du mail via Gemini ou fallback manuel."""
    prompt = f"Rédige un mail professionnel court pour notifier un refus de marchandise au magasin {magasin}. Fournisseur: {fournisseur}, BL: {bl}. Motif du refus: {commentaire}. Signé: Service Logistique."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={apiKey}"
    try:
        response = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except:
        return f"Bonjour,\n\nRefus BL {bl} du fournisseur {fournisseur} au magasin {magasin}.\nMotif: {commentaire}\n\nCordialement,\nService Logistique"


def extreme_clean(text):
    """Supprime radicalement les espaces invisibles et caractères non-ASCII pour le protocole SMTP"""
    if not isinstance(text, str):
        return str(text)
    text = text.replace('\xa0', ' ')
    # Garde uniquement les caractères imprimables standards pour les paramètres de connexion
    return re.sub(r'[^\x20-\x7E]', '', text).strip()


def load_mail_list_v2():
    """Charge les noms et emails depuis l'onglet MAIL (Colonnes A et B)"""
    try:
        gc = authenticate_gsheet()
        if not gc: return {}
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_MAILS)
        # Récupère toutes les valeurs des colonnes A (Nom) et B (Mail)
        data = ws.get_all_values()
        if not data:
            return {}
        
        mapping = {}
        for row in data:
            if len(row) >= 2:
                nom = str(row[0]).strip()
                email = str(row[1]).strip()
                if "@" in email:
                    # On crée une étiquette lisible "Nom (email)"
                    label = f"{nom} ({email})" if nom and nom.lower() != "nom" else email
                    mapping[label] = email
        return mapping
    except Exception:
        return {}

        

# --- APPLICATION ------------------------------------------------------------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Logistique Réception", layout="wide", page_icon="📦")

    # CSS Custom pour améliorer le look
    st.markdown("""
        <style>
        .main { background-color: #f8fafc; }
        .stButton>button { border-radius: 8px; }
        </style>
    """, unsafe_allow_html=True)
    
    if 'page' not in st.session_state: st.session_state.page = 'dashboard'

 # Menu latéral
    with st.sidebar:
        st.title("📦 Logistique")
        st.info(f"Connecté au Sheet : {WS_DATA}")
        
        pages = {
            'dashboard': "📊 Tableau de Bord",
			'debug': "🔍 Vérifier la connexion GSheet",
            'refus': "🚚 Refus de marchandise ⚠️",
            'transport': "🚚 Suivi Transport",
            'pdc': "⚠️ Pas de Commande",
            'import': "📥 Import Excel",
            'emplacements': "📍 Emplacements",
            'deballage': "⚙️ Déballage",
            'litige': "⚙️ Litiges",
            'hist': "📜 Historique Global"
        }
        
        for key, label in pages.items():
            if st.button(label, use_container_width=True, type="primary" if st.session_state.page == key else "secondary"):
                st.session_state.page = key
        
        st.divider()
        if st.button("🔄 Actualiser les données"):
            st.rerun()
            
    # Chargement initial des données
    df_all = load_data(WS_DATA,COLUMNS_DATA)

    # --- PAGE ACCUEIL 
    if st.session_state.page == 'dashboard':
        st.header("📊 Tableau de Bord Réception")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Réceptions", len(df_all))
        col2.metric("À déballer", len(df_all[df_all['StatutBL'] == 'À déballer']))
        col3.metric("Litiges", len(df_all[df_all['StatutBL'] == 'LITIGE']))
        col4.metric("Terminées", len(df_all[df_all['StatutBL'].isin(['TERMINEE', 'Clôturé'])]))
        
        st.subheader("Dernières réceptions")
        st.dataframe(df_all.head(10), use_container_width=True)
    
	# --- PAGE REFUS DE MARCHANDISE---
    # --- Lié à la page REFUS  ---
    elif st.session_state.page == 'refus':
        st.title("🚚 Déclaration de Refus")
        
        # Pré-chargement des contacts
        contacts_map = load_mail_list_v2()
        liste_labels = list(contacts_map.keys())
        
        with st.form("main_form_refus", clear_on_submit=True):
            st.subheader("Détails de la livraison")
            col1, col2 = st.columns(2)
            with col1:
                f_magasin = st.selectbox("Magasin", ["BAYONNE", "BIDART", "URRUGNE", "PMI"])
                f_date = st.date_input("Date du refus", datetime.now())
            with col2:
                f_fourn = st.text_input("Fournisseur")
                f_bl = st.text_input("Numéro de BL")
            
            st.divider()
            
            # Gestion des mails
            f_emails_choisis = []
            if not liste_labels:
                st.warning("⚠️ Aucun contact trouvé dans 'MAIL'.")
                f_manual = st.text_input("Saisir emails manuels (séparés par virgule) :")
                f_emails_choisis = [e.strip() for e in f_manual.split(",") if "@" in e]
            else:
                selection = st.multiselect(
                    "Destinataires :",
                    options=liste_labels,
                    help="Sélectionnez les noms ou tapez un mail + Entrée."
                )
                for item in selection:
                    if item in contacts_map:
                        f_emails_choisis.append(contacts_map[item])
                    elif "@" in item:
                        f_emails_choisis.append(item.strip())
            
            f_comment = st.text_area("Commentaire / Motif")
            f_file = st.file_uploader("Preuve / Photo", type=["jpg", "png", "pdf"])
            
            # Bouton de validation (OBLIGATOIRE DANS LE FORM)
            submit = st.form_submit_button("🚀 Enregistrer et Envoyer")
            
            if submit:
                if f_fourn and f_bl and f_emails_choisis:
                    with st.spinner("Traitement logistique..."):
                        row = [f_magasin, str(f_date), f_fourn, f_bl, f_comment]
                        if add_row_gsheet(WS_REFUS, row):
                            # IA ou message manuel
                            contenu = generate_ai_content(f_magasin, f_fourn, f_bl, f_comment)
                            
                            # ENVOI DU MAIL avec la variable f_emails_choisis
                            success, msg = send_actual_email(f_emails_choisis, f"REFUS MARCHANDISE : {f_fourn}", contenu, f_file)
                            
                            if success:
                                st.balloons()						
                                st.success(f"✅ Refus enregistré et mail envoyé.")
                                st.toast("Remise à zéro du formulaire...", icon="🔄")

                            else:
                                st.error(f"❌ GSheet OK mais erreur mail : {msg}")
                        else:
                            st.error("❌ Erreur lors de l'enregistrement GSheet.")
                else:
                    st.error("⚠️ Veuillez remplir le Fournisseur, le BL et au moins un destinataire.")

        # Affichage de l'historique
        st.divider()
        st.subheader("📜 Historique des refus")
        st.info("💡 Utilisez les cases vides sous les titres de colonnes pour filtrer.")
        df_refus = load_data(WS_REFUS, COLUMNS_REFUS)        
        if not df_refus.empty:
            # Extraction EXCEL rapide
            excel_data = to_excel(df_refus)
            st.download_button(
                label="📥 Extraire les données (EXCEL)",
                data=excel_data,
                file_name=f'refus_logistique_{datetime.now().strftime("%Y%m%d")}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            grid_options = get_standard_grid_options(df_refus)
            
            # --- 2. EMPLACEMENT UTILISATION ---
            AgGrid(
                df_refus, 
                gridOptions=grid_options, 
                theme='balham',
                height=600, 
                width='100%',
                update_mode=GridUpdateMode.VALUE_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                allow_unsafe_jscode=True
            )
        else:
            st.info("Aucun refus enregistré.")

    # --- PAGE 2 : SUIVI TRANSPORT ---
    # --- Lié à la page TRANSPORT  ---
    elif st.session_state.page == 'transport':
        st.title("🚛 Arrivée d'un transporteur")
        
        # Chargement historique pour calcul de l'ID auto
        df_transp = load_data(WS_TRANSPORT, COLUMNS_TRANSPORT)
        next_id = len(df_transp) + 1
        
        with st.form("form_transport", clear_on_submit=True):
            st.subheader(f"Saisie Transport n°{next_id}")
            c1, c2 = st.columns(2)
            with c1:
                t_magasin = st.selectbox("Magasin", ["BAYONNE", "BIDART", "URRUGNE", "PMI"], key="t_mag")
                t_nom = st.text_input("Nom du Transporteur")
                t_palettes = st.number_input("Nombre de palettes", min_value=0, step=1)
            with c2:
                t_poids = st.number_input("Poids total (kg)", min_value=0.0, step=0.5)
                t_abime = st.selectbox("Colis abîmé ou ouvert ?", ["NON", "OUI"])
                t_litige = st.selectbox("Litige à la réception ?", ["NON", "OUI"])
            
            t_comment = st.text_area("Commentaire Livraison")
            
            submit_t = st.form_submit_button("🏁 Valider l'arrivée")
            
            if submit_t:
                if t_nom:
                    with st.spinner("Enregistrement transporteur..."):
                        row_t = [next_id, t_magasin, t_nom, t_palettes, t_poids, t_comment, t_abime, t_litige]
                        if add_row_gsheet(WS_TRANSPORT, row_t):
                            st.success(f"✅ Transport n°{next_id} enregistré !")
                            #st.balloons()
                            #st.rerun()

                        else:
                            st.error("❌ Erreur lors de l'enregistrement.")
                else:
                    st.error("⚠️ Veuillez saisir le nom du transporteur.")					

        st.divider()
        st.subheader("📜 Historique des Transports")
        
        # Chargement propre des données pour l'historique
        df_historique = load_data(WS_TRANSPORT, COLUMNS_TRANSPORT)
			
        if not df_historique.empty:
            AgGrid(df_historique, gridOptions=get_standard_grid_options(df_historique), height=400, theme='balham', key="grid_t_page_final")
        else:
            st.info("Aucun transport dans l'historique.")

		st.rerun()
	
    elif st.session_state.page == 'debug':
        st.title("🔍 Diagnostic de Connexion")
        try:
            gc = authenticate_gsheet()
            sh = gc.open_by_key(SHEET_ID)
            st.success(f"✅ Connecté au Google Sheet : {sh.title}")
            
            onglets = [w.title for w in sh.worksheets()]
            st.write(f"Onglets trouvés : {onglets}")
            
            if WS_TRANSPORT in onglets:
                ws = sh.worksheet(WS_TRANSPORT)
                header = ws.row_values(1)
                st.write(f"✅ Onglet '{WS_TRANSPORT}' trouvé.")
                st.write(f"Colonnes actuelles dans GSheet : {header}")
                st.write(f"Colonnes attendues par Python : {COLUMNS_TRANSPORT}")
                
                test_data = ws.get_all_records()
                st.write(f"Nombre de lignes de données : {len(test_data)}")
                if test_data:
                    st.json(test_data[0])
            else:
                st.error(f"❌ L'onglet '{WS_TRANSPORT}' est introuvable !")
                if st.button("Créer l'onglet TRANSPORT"):
                    sh.add_worksheet(title=WS_TRANSPORT, rows="100", cols="20")
                    sh.worksheet(WS_TRANSPORT).append_row(COLUMNS_TRANSPORT)
                    st.rerun()
        except Exception as e:
            st.error(f"Erreur de diagnostic : {e}")
			
    # --- PAGE 3 : PAS DE COMMANDE ---
    # --- Lié à la page PDC  ---
    elif st.session_state.page == 'pdc':
        st.header("⚠️ Gestion des 'Pas de Commande'")
        df_all = load_data(WS_DATA, COLUMNS_DATA)
        # On filtre par exemple sur un statut spécifique ou l'absence de numéro de commande
        # Ici on affiche tout ce qui est marqué en litige ou spécifique "Sans commande"
        df_target = df_all[df_all['StatutBL'].str.contains('Commande', case=False, na=False) | (df_all['StatutBL'] == 'LITIGE')].copy()
        
        if df_target.empty:
            st.info("Aucun dossier 'Pas de Commande' identifié.")
        else:
            grid_res = render_advanced_grid(
                df_target[['NumReception', 'Fournisseur', 'StatutBL', 'Commentaire_litige', 'Date Clôture']],
                editable_cols=['StatutBL', 'Commentaire_litige', 'Date Clôture']
            )
            if st.button("💾 Actualiser les dossiers"):
                if update_multiple_rows(grid_res['data']):
                    st.success("Dossiers mis à jour.")
                    st.rerun()


    # ---  IMPORT EXCEL ---
    # --- Lié à la page DATA  ---
    elif st.session_state.page == 'import':
        st.header("📥 Import des nouvelles réceptions")
        st.write("Le fichier Excel doit contenir au minimum : `NumReception`, `Fournisseur`, `Livré le`")
        uploaded_file = st.file_uploader("Fichier Excel", type=['xlsx', 'xls'])
        
        if uploaded_file:
            df_upload = pd.read_excel(uploaded_file)
            st.write(f"Aperçu ({len(df_upload)} lignes) :")
            st.dataframe(df_upload.head())
            
            if st.button("🚀 Ajouter au Google Sheet"):
                # On prépare les données pour matcher exactement les colonnes
                df_to_append = df_upload.reindex(columns=COLUMNS_DATA).fillna('')
                # On concatène avec l'existant
                df_final = pd.concat([df_all, df_to_append], ignore_index=True)
                
                if save_data_to_gsheet(df_final):
                    st.success("Import réussi !")
                    st.rerun()

    # --- EMPLACEMENTS ---
    # --- Lié à la page DATA  ---
    elif st.session_state.page == 'emplacements':
        st.header("📍 Attribution des Emplacements")
        mask = (df_all['Emplacement'] == "") | (df_all['Emplacement'].isna())
        df_target = df_all[mask].copy()
        
        if df_target.empty:
            st.success("Toutes les réceptions ont un emplacement !")
            if st.button("Voir tout"): render_custom_grid(df_all)
        else:
            grid_res = render_custom_grid(
                df_target[['NumReception', 'Fournisseur', 'Livré le', 'Qté', 'Emplacement']],
                editable_cols=['Emplacement']
            )
            if st.button("💾 Sauvegarder les Emplacements"):
                df_updated = df_all.copy()
                new_entries = pd.DataFrame(grid_res['data'])
                for _, row in new_entries.iterrows():
                    df_updated.loc[df_updated['NumReception'] == row['NumReception'], 'Emplacement'] = row['Emplacement']
                
                if save_data_to_gsheet(df_updated):
                    st.success("Emplacements enregistrés.")
                    st.rerun()

    # --- DÉBALLAGE ---
    # --- Lié à la page DATA  ---
    elif st.session_state.page == 'deballage':
        st.header("⚙️ Suivi du Déballage ")
        # Filtrer pour ne pas montrer ce qui est déjà fini depuis longtemps si nécessaire
        df_target = df_all[df_all['StatutBL'] != 'TERMINEE'].copy()
        
        grid_res = render_custom_grid(
            df_target[['NumReception', 'Fournisseur', 'StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige']],
            editable_cols=['StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige'],
            status_options=['À déballer', 'EN COURS', 'TERMINEE', 'LITIGE', 'A_DEBALLER']
        )
        
        if st.button("💾 Enregistrer les modifications de déballage"):
            df_updated = df_all.copy()
            updated_rows = pd.DataFrame(grid_res['data'])
            for _, row in updated_rows.iterrows():
                for col in ['StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige']:
                    df_updated.loc[df_updated['NumReception'] == row['NumReception'], col] = row[col]
            
            if save_data_to_gsheet(df_updated):
                st.success("Mise à jour effectuée !")
                st.rerun()
                
    # --- PAGE 7 : LITIGES ---
    # --- Lié à la page LITIGES  ---
    elif st.session_state.page == 'litige':
        st.header("⚙️ Suivi des Litiges")
        # Filtrer pour ne pas montrer ce qui est déjà fini depuis longtemps si nécessaire
        df_target = df_all[df_all['StatutBL'] != 'TERMINEE'].copy()
        
        grid_res = render_custom_grid(
            df_target[['NumReception', 'Fournisseur', 'StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige']],
            editable_cols=['StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige'],
            status_options=['À déballer', 'EN COURS', 'TERMINEE', 'LITIGE', 'A_DEBALLER']
        )
        
        if st.button("💾 Enregistrer les modifications de déballage"):
            df_updated = df_all.copy()
            updated_rows = pd.DataFrame(grid_res['data'])
            for _, row in updated_rows.iterrows():
                for col in ['StatutBL', 'NomDeballage', 'LitigesCompta', 'Commentaire_litige']:
                    df_updated.loc[df_updated['NumReception'] == row['NumReception'], col] = row[col]
            
            if save_data_to_gsheet(df_updated):
                st.success("Mise à jour effectuée !")
                st.rerun()
    
    # --- PAGE HISTORIQUE---    
    # --- Lié à la page DATA  ---
    elif st.session_state.page == 'hist':
        st.header("📜 Historique Complet")
        render_custom_grid(df_all)

if __name__ == "__main__":
    main()
