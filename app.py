import pytz
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re
import time
import io
from fpdf import FPDF
import google.generativeai as genai
import json

# --- INITIALIZE SESSION STATE ---
if 'scanned_date' not in st.session_state: st.session_state.scanned_date = date.today()
if 'scanned_total' not in st.session_state: st.session_state.scanned_total = 0.0
if 'scanned_pin' not in st.session_state: st.session_state.scanned_pin = ""

# Setup Gemini
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

def scan_receipt_with_ai(uploaded_file):
    model = genai.GenerativeModel('gemini-1.5-flash')
    mime_type = uploaded_file.type 
    file_bytes = uploaded_file.getvalue()
    
    prompt = """
    Analyze this document (eTIMS receipt or invoice). 
    Return ONLY a JSON object with these keys: 
    'date' (YYYY-MM-DD), 'total' (number), 'pin' (Seller KRA PIN), 'vat' (number).
    If it is a PDF with multiple pages, only analyze the first page.
    If a value is missing, use null.
    """
    
    response = model.generate_content([
        prompt, 
        {'mime_type': mime_type, 'data': file_bytes}
    ])
    
    try:
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except:
        return None
        
# --- 1. INITIALIZE GLOBAL VARIABLES & CONFIG ---
st.set_page_config(page_title="GEMPS 🇰🇪 VAT Tracker", layout="wide", page_icon="🇰🇪")
kenya_tz = pytz.timezone('Africa/Nairobi')
now_kenya = datetime.now(kenya_tz)

CURRENT_VAT_RATE = 0.16  
VAT_MULTIPLIER = 1 + CURRENT_VAT_RATE 

# --- 2. CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 3. HELPER FUNCTIONS ---
@st.cache_data(ttl=300)
def get_recent_pins_cached(_conn, pin_owner):
    try:
        s_df = _conn.read(worksheet="Sales", ttl=0)
        p_df = _conn.read(worksheet="Purchases", ttl=0)
        s_pins = s_df[s_df['UserPIN'] == pin_owner]['CounterpartyPIN'].tolist() if not s_df.empty else []
        p_pins = p_df[p_df['UserPIN'] == pin_owner]['CounterpartyPIN'].tolist() if not p_df.empty else []
        return sorted(list(set(str(p) for p in s_pins + p_pins if p)))
    except: return []

@st.cache_data(ttl=300)
def get_all_user_pins(_conn):
    try:
        s_df = _conn.read(worksheet="Sales", ttl=0)
        p_df = _conn.read(worksheet="Purchases", ttl=0)
        s_pins = s_df['UserPIN'].tolist() if not s_df.empty else []
        p_pins = p_df['UserPIN'].tolist() if not p_df.empty else []
        return sorted(list(set(str(p) for p in s_pins + p_pins if p)))
    except: return []

@st.cache_data(ttl=60)
def get_stats_cached(_conn, pin, current_filter):
    try:
        s_df = _conn.read(worksheet="Sales", ttl=0)
        p_df = _conn.read(worksheet="Purchases", ttl=0)
        c_sales = s_df[(s_df['UserPIN'] == pin) & (s_df['Date'].astype(str).str.startswith(current_filter))]
        c_purch = p_df[(p_df['UserPIN'] == pin) & (p_df['Date'].astype(str).str.startswith(current_filter))]
        out_v = c_sales['VAT'].astype(float).sum() if not c_sales.empty else 0.0
        in_v = c_purch['VAT'].astype(float).sum() if not c_purch.empty else 0.0
        return out_v, in_v
    except: return 0.0, 0.0

def generate_excel_template():
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        cols = ["Date (YYYY-MM-DD)", "CounterpartyPIN", "Amount", "VAT_Type (Inclusive/Exclusive/Exempt)"]
        pd.DataFrame(columns=cols).to_excel(writer, sheet_name='Sales', index=False)
        pd.DataFrame(columns=cols).to_excel(writer, sheet_name='Purchases', index=False)
    return output.getvalue()

def create_full_vat_report(s_data, p_data, pin, period, o_v, i_v, n_v):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    def clean_text(text): return str(text).encode('ascii', 'ignore').decode('ascii')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="GEMPS KE VAT Reconciliation Report", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=clean_text(f"Generated on: {now_kenya.strftime('%d %b %Y %H:%M')}"), ln=True, align='C')
    pdf.ln(5)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, clean_text(f" KRA PIN: {pin} | Period: {period}"), 1, 1, 'C', True)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(63, 10, "Output VAT (Sales)", 1, 0, 'C')
    pdf.cell(63, 10, "Input VAT (Purchases)", 1, 0, 'C')
    pdf.cell(64, 10, "Net VAT Payable/(Credit)", 1, 1, 'C')
    pdf.set_font("Arial", size=11)
    pdf.cell(63, 10, f"KES {o_v:,.2f}", 1, 0, 'C')
    pdf.cell(63, 10, f"KES {i_v:,.2f}", 1, 0, 'C')
    pdf.cell(64, 10, f"KES {n_v:,.2f}", 1, 1, 'C')
    pdf.ln(10)
    def build_table(header_text, df):
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, header_text, 0, 1, 'C')
        pdf.set_fill_color(31, 119, 180); pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(40, 8, "Date", 1, 0, 'C', True)
        pdf.cell(60, 8, "Counterparty PIN", 1, 0, 'C', True)
        pdf.cell(45, 8, "Total (KES)", 1, 0, 'C', True)
        pdf.cell(45, 8, "VAT (KES)", 1, 1, 'C', True)
        pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", size=9)
        if df.empty: pdf.cell(190, 8, "No records found.", 1, 1, 'C')
        else:
            for _, row in df.iterrows():
                pdf.cell(40, 8, clean_text(row['Date']), 1, 0, 'C')
                pdf.cell(60, 8, clean_text(row['CounterpartyPIN']), 1, 0, 'C')
                pdf.cell(45, 8, f"{row['Total']:,.2f}", 1, 0, 'C')
                pdf.cell(45, 8, f"{row['VAT']:,.2f}", 1, 1, 'C')
        pdf.ln(5)
    build_table("1. Sales Transactions (Output)", s_data)
    build_table("2. Purchase Transactions (Input)", p_data)
    pdf.set_y(-25); pdf.set_font("Arial", 'I', 8)
    pdf.cell(0, 10, "Computer-generated summary by GEMPS KE. Verify with KRA eTIMS.", 0, 0, 'C')
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 4. MOBILE UI CSS ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #1f77b4; }
    div[data-testid="metric-container"] { 
        background-color: #ffffff; border: 2px solid #f0f2f6; 
        padding: 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); 
    }
    @media (max-width: 640px) {
        .main .block-container { padding: 1rem 0.5rem; }
        .stButton>button { width: 100% !important; height: 3.5rem !important; border-radius: 12px !important; }
    }
    </style>
""", unsafe_allow_html=True)

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("🏢 GEMPS 🇰🇪")
    
    # CHANGE 1: Retention/Suggestion for User PIN
    known_user_pins = get_all_user_pins(conn)
    u_pin_choice = st.selectbox("Your KRA PIN", ["Enter New PIN..."] + known_user_pins)
    if u_pin_choice == "Enter New PIN...":
        kra_pin_raw = st.text_input("Input New KRA PIN", placeholder="e.g., A012345678Z")
    else:
        kra_pin_raw = u_pin_choice

    kra_pin = kra_pin_raw.upper().strip()
    is_valid_pin = bool(re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin))
    
    # CHANGE 3: Permanent PIN Verified notification
    if kra_pin:
        if not is_valid_pin: 
            st.warning("⚠️ Invalid PIN format.")
        else: 
            st.success("✅ PIN Verified")
    
    st.divider()
    # Toggle for VAT calculations (Used in Change 4)
    enable_vat_calc = st.toggle("Enable VAT Calculations", value=True)
    
    today = now_kenya.date()
    deadline = date(today.year, today.month, 20) if today.day <= 20 else \
               (date(today.year + 1, 1, 20) if today.month == 12 else date(today.year, today.month + 1, 20))
    st.metric("Days to Next Deadline", f"{(deadline - today).days} Days")
    st.caption(f"Time: {now_kenya.strftime('%d %b %Y %H:%M')}")
    
    st.divider()
    st.subheader("Bulk Upload")
    st.download_button("Download Excel Template", generate_excel_template(), "BulkVAT_template.xlsx")
    uploaded_file = st.file_uploader("📤 Upload filled template", type=["xlsx"])

# --- 6. MAIN INTERFACE ---
st.title("GEMPS 🇰🇪 VAT Tracker")

if kra_pin and is_valid_pin:
    current_filter = now_kenya.strftime('%Y-%m')
    live_out, live_in = get_stats_cached(conn, kra_pin, current_filter)
    net_payable = live_out - live_in
    
    st.subheader(f"📊 {now_kenya.strftime('%B %Y')} Live Status")
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Sales VAT", f"KES {live_out:,.0f}")
    with c2: st.metric("Purchase VAT", f"KES {live_in:,.0f}")
    with c3: 
        st.metric("Net Position", f"KES {abs(net_payable):,.0f}", 
                  delta="Due to KRA" if net_payable > 0 else "VAT Credit",
                  delta_color="inverse" if net_payable > 0 else "normal")
    st.divider()
else:
    st.info("👋 Welcome! Enter your KRA PIN in the sidebar to view your live VAT dashboard.")

# --- 7. TABS ---
tab1, tab2, tab3 = st.tabs(["➕ Single Entry", "📑 Bulk Queue", "📊 Monthly Report"])

with tab1:
    if not kra_pin:
        st.info("👋 Enter KRA PIN in sidebar to start.")
    else:
        with st.expander("📸 AI Receipt Scanner & PDF Reader", expanded=False):
            input_method = st.radio("Select Input", ["Camera", "Upload File"], horizontal=True)
            uploaded_doc = st.camera_input("Snap photo") if input_method == "Camera" else st.file_uploader("Upload Image/PDF", type=["pdf", "png", "jpg", "jpeg"])
            
            if uploaded_doc:
                if st.button("🚀 Process with AI", use_container_width=True):
                    try:
                        with st.spinner("Gemini is reading..."):
                            extracted_data = scan_receipt_with_ai(uploaded_doc)
                            if extracted_data:
                                st.session_state.scanned_total = float(extracted_data.get('total', 0.0))
                                st.session_state.scanned_pin = str(extracted_data.get('pin', "")).upper()
                                raw_date = extracted_data.get('date')
                                try:
                                    st.session_state.scanned_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
                                except:
                                    st.session_state.scanned_date = date.today()
                                st.toast("✅ Data Extracted!") 
                            else:
                                st.error("AI couldn't find data.")
                    except Exception as e:
                        st.error(f"AI Error: {e}")

        st.divider()

        with st.form("transaction_form", clear_on_submit=True):
            t_type = st.selectbox("Category", ["Sales (Output VAT)", "Purchase (Input VAT)"])
            col1, col2 = st.columns(2)
            with col1:
                t_date = st.date_input("Invoice Date", value=st.session_state.get('scanned_date', date.today()))
                amount = st.number_input("Total Amount (KES)", min_value=0.0, step=1.0, value=st.session_state.get('scanned_total', 0.0))
            
            with col2:
    # 1. Check for AI detected PIN first
    s_pin = st.session_state.get('scanned_pin', "")
    recent_pins = get_recent_pins_cached(conn, kra_pin)
    
    # 2. Use a hybrid selection/input logic
    # This allows users to either select from a list OR type a completely new PIN
    if s_pin:
        other_pin = st.text_input("Counterparty PIN (Detected)", value=s_pin).upper().strip()
    else:
        # We use a placeholder to guide the user that they can type anything
        other_pin = st.selectbox(
            "Counterparty PIN (Select or type to search)",
            options=[""] + recent_pins + ["➕ New PIN..."],
            index=0,
            help="Select an existing PIN or click 'New PIN' to enter a manual one."
        )
        
        # If the user selects "New PIN", show the manual entry box
        if other_pin == "➕ New PIN...":
            other_pin = st.text_input("Manual PIN Entry", placeholder="Enter PIN (e.g., P051796617P)").upper().strip()

    is_etims = st.toggle("eTIMS Certified?", value=True)
    
    # 3. VAT Calculations Toggle
    if enable_vat_calc:
        calc_mode = st.radio("Pricing", ["VAT Inclusive", "VAT Exclusive"], horizontal=True)
    else:
        calc_mode = "VAT Exempt"

            if st.form_submit_button("Save to Cloud", use_container_width=True):
                if not other_pin or other_pin == kra_pin: 
                    st.error("⚠️ Invalid Counterparty PIN.")
                elif amount <= 0: 
                    st.warning("⚠️ Amount must be > 0.")
                else:
                    try:
                        # Logic for VAT Value based on Toggle (Change 4)
                        if enable_vat_calc:
                            v_val = (amount - (amount/VAT_MULTIPLIER)) if calc_mode == "VAT Inclusive" else (amount * CURRENT_VAT_RATE)
                            t_save = amount if calc_mode == "VAT Inclusive" else (amount + v_val)
                        else:
                            v_val = 0.0
                            t_save = amount
                        
                        s_name = "Sales" if "Sales" in t_type else "Purchases"
                        df = conn.read(worksheet=s_name, ttl=0)
                        new_row = pd.DataFrame([{
                            "UserPIN": kra_pin, "Date": str(t_date), "CounterpartyPIN": other_pin, 
                            "Total": int(round(t_save)), "VAT": int(round(v_val)), "eTIMS": "Yes" if is_etims else "No"
                        }])
                        conn.update(worksheet=s_name, data=pd.concat([df, new_row], ignore_index=True))
                        st.success(f"✅ Saved to {s_name}!")
                        st.balloons()
                        st.session_state.scanned_date = date.today()
                        st.session_state.scanned_total = 0.0
                        st.session_state.scanned_pin = ""
                        time.sleep(1)
                        st.rerun() 
                    except Exception as e: 
                        st.error(f"Error saving: {e}")

with tab2:
    if not kra_pin: st.info("👋 Enter KRA PIN in sidebar.")
    elif uploaded_file:
        try:
            up_sales = pd.read_excel(uploaded_file, sheet_name='Sales')
            up_purch = pd.read_excel(uploaded_file, sheet_name='Purchases')
            def proc(df, is_s):
                if df.empty: return pd.DataFrame()
                res = []
                for _, r in df.dropna(subset=['Amount']).iterrows():
                    amt = float(r['Amount'])
                    vt = str(r.get('VAT_Type (Inclusive/Exclusive/Exempt)', 'Exempt'))
                    v = (amt - (amt/VAT_MULTIPLIER)) if "Inclusive" in vt else (amt*0.16 if "Exclusive" in vt else 0)
                    t = amt if "Inclusive" in vt else (amt + v if "Exclusive" in vt else amt)
                    res.append({"UserPIN": kra_pin, "Date": str(r.get('Date (YYYY-MM-DD)', today)).split(" ")[0], "CounterpartyPIN": str(r.get('CounterpartyPIN', '')), "Total": int(round(t)), "VAT": int(round(v)), "eTIMS": "Yes", "Category": "Sales" if is_s else "Purchases"})
                return pd.DataFrame(res)
            q_df = pd.concat([proc(up_sales, True), proc(up_purch, False)], ignore_index=True)
            if not q_df.empty:
                edited = st.data_editor(q_df, use_container_width=True, hide_index=True, num_rows="dynamic")
                if st.button("🚀 Push Queue to Cloud"):
                    for cat in ["Sales", "Purchases"]:
                        sub = edited[edited['Category'] == cat].drop(columns=['Category'])
                        if not sub.empty:
                            exist = conn.read(worksheet=cat, ttl=0)
                            conn.update(worksheet=cat, data=pd.concat([exist, sub], ignore_index=True))
                    st.success("✅ Bulk Upload Complete!")
            else: st.warning("File is empty.")
        except Exception as e: st.error(f"Excel Error: {e}")

with tab3:
    if not kra_pin: st.info("👋 Enter KRA PIN in sidebar.")
    else:
        cm, cy = st.columns(2)
        months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        sel_m = cm.selectbox("Month", months, index=now_kenya.month-1)
        sel_y = cy.selectbox("Year", range(2024, now_kenya.year + 2), index=now_kenya.year-2024)
        f_str = f"{sel_y}-{months.index(sel_m)+1:02d}"

        if st.button(f"Generate Report for {sel_m} {sel_y}"):
            s_df = conn.read(worksheet="Sales", ttl=0)
            p_df = conn.read(worksheet="Purchases", ttl=0)
            u_s = s_df[(s_df['UserPIN'] == kra_pin) & (s_df['Date'].astype(str).str.startswith(f_str))] if s_df is not None else pd.DataFrame()
            u_p = p_df[(p_df['UserPIN'] == kra_pin) & (p_df['Date'].astype(str).str.startswith(f_str))] if p_df is not None else pd.DataFrame()
            ov, iv = u_s['VAT'].astype(float).sum() if not u_s.empty else 0.0, u_p['VAT'].astype(float).sum() if not u_p.empty else 0.0
            st.session_state.report_data = {"u_s": u_s, "u_p": u_p, "o_v": ov, "i_v": iv, "n_v": ov-iv, "period": f"{sel_m} {sel_y}"}

        if rd := st.session_state.get("report_data"):
            m1, m2, m3 = st.columns(3)
            m1.metric("Output VAT", f"KES {rd['o_v']:,.0f}")
            m2.metric("Input VAT", f"KES {rd['i_v']:,.0f}")
            m3.metric("Net VAT", f"KES {abs(rd['n_v']):,.0f}", delta="Due" if rd['n_v']>0 else "Credit")

            st.write("---")
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            with btn_col1:
                if st.button("📄 Prepare Final PDF", use_container_width=True):
                    st.session_state.pdf_report_bytes = create_full_vat_report(rd["u_s"], rd["u_p"], kra_pin, rd["period"], rd["o_v"], rd["i_v"], rd["n_v"])
            with btn_col2:
                pdf_data = st.session_state.get("pdf_report_bytes")
                st.download_button(label="📥 Download PDF", data=pdf_data if pdf_data else b"", file_name=f"VAT_Report_{rd['period']}.pdf", mime="application/pdf", use_container_width=True, disabled=not pdf_data)
            with btn_col3:
                if st.button("🔄 Clear Report", use_container_width=True):
                    st.session_state.report_data = None
                    st.session_state.pdf_report_bytes = None
                    st.rerun()
