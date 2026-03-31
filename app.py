import pytz
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re
import time
import io
import uuid
from fpdf import FPDF
import google.generativeai as genai
import json

# --- 1. INITIALIZE CONFIG & SESSION STATE ---
st.set_page_config(page_title="GEMPS 🇰🇪 VAT Tracker", layout="wide", page_icon="🇰🇪")

if 'scanned_date' not in st.session_state: st.session_state.scanned_date = None
if 'scanned_total' not in st.session_state: st.session_state.scanned_total = 0.0
if 'scanned_pin' not in st.session_state: st.session_state.scanned_pin = ""
if 'report_data' not in st.session_state: st.session_state.report_data = None

kenya_tz = pytz.timezone('Africa/Nairobi')
now_kenya = datetime.now(kenya_tz)
CURRENT_VAT_RATE = 0.16  
VAT_MULTIPLIER = 1 + CURRENT_VAT_RATE 

# Setup Gemini
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# --- 2. CONNECTION & CACHING ---
conn = st.connection("gsheets", type=GSheetsConnection)

def refresh_data():
    """Clears cache to force fresh data from Google Sheets."""
    st.cache_data.clear()
    st.toast("🔄 Data Synced with Cloud!")
    time.sleep(0.5)

@st.cache_data(ttl=300)
def get_stats_cached(_conn, pin, current_filter):
    try:
        s_df = _conn.read(worksheet="Sales", ttl=0)
        p_df = _conn.read(worksheet="Purchases", ttl=0)
        c_sales = s_df[(s_df['UserPIN'] == pin) & (s_df['Date'].astype(str).str.startswith(current_filter))]
        c_purch = p_df[(p_df['UserPIN'] == pin) & (p_df['Date'].astype(str).str.startswith(current_filter))]
        out_v = c_sales['VAT'].astype(float).sum() if not c_sales.empty else 0.0
        in_v = c_purch['VAT'].astype(float).sum() if not c_purch.empty else 0.0
        return out_v, in_v, c_sales # Return sales for the trend chart
    except: return 0.0, 0.0, pd.DataFrame()

# --- 3. LOGIC FUNCTIONS ---
def scan_receipt_with_ai(uploaded_file):
    model = genai.GenerativeModel('gemini-1.5-flash')
    file_bytes = uploaded_file.getvalue()
    mime_type = uploaded_file.type or "image/jpeg"

    prompt = """Analyze this eTIMS receipt/invoice. Return ONLY a JSON object: 
    {'date': 'YYYY-MM-DD', 'total': number, 'pin': 'Seller PIN', 'vat': number}. 
    If missing, use null."""
    
    try:
        response = model.generate_content([prompt, {'mime_type': mime_type, 'data': file_bytes}])
        clean_json = re.sub(r'```json|```', '', response.text).strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI Read Error: {e}")
        return None

def create_full_vat_report(s_data, p_data, pin, period, o_v, i_v, n_v):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="GEMPS KE VAT Reconciliation Report", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"KRA PIN: {pin} | Period: {period}", ln=True, align='C')
    pdf.ln(10)
    pdf.cell(0, 10, f"Net VAT Position: KES {n_v:,.2f}", 1, 1, 'C')
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("🏢 GEMPS 🇰🇪")
    kra_pin_raw = st.text_input("Your KRA PIN", placeholder="e.g., A012345678Z")
    kra_pin = kra_pin_raw.upper().strip()
    
    is_valid_pin = bool(re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin))
    if kra_pin and not is_valid_pin: st.warning("⚠️ Invalid PIN format.")
    elif kra_pin: st.success("✅ PIN Verified")
    
    if st.button("🔄 Sync with Cloud", use_container_width=True):
        refresh_data()
        st.rerun()

    st.divider()
    today = now_kenya.date()
    deadline = date(today.year, today.month, 20) if today.day <= 20 else \
               (date(today.year + 1, 1, 20) if today.month == 12 else date(today.year, today.month + 1, 20))
    st.metric("Days to KRA Deadline", f"{(deadline - today).days} Days")

# --- 5. MAIN DASHBOARD ---
st.title("GEMPS 🇰🇪 VAT Tracker")

if kra_pin and is_valid_pin:
    current_filter = now_kenya.strftime('%Y-%m')
    live_out, live_in, sales_df = get_stats_cached(conn, kra_pin, current_filter)
    net_payable = live_out - live_in
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Sales VAT (Output)", f"KES {live_out:,.0f}")
    c2.metric("Purchase VAT (Input)", f"KES {live_in:,.0f}")
    c3.metric("Net Position", f"KES {abs(net_payable):,.0f}", 
              delta="Due to KRA" if net_payable > 0 else "VAT Credit",
              delta_color="inverse" if net_payable > 0 else "normal")

    if not sales_df.empty:
        with st.expander("📈 VAT Performance Trend"):
            chart_data = sales_df.groupby('Date')['VAT'].sum()
            st.line_chart(chart_data)
else:
    st.info("👋 Welcome! Enter your KRA PIN in the sidebar to view your dashboard.")

# --- 6. TABS ---
tab1, tab2, tab3 = st.tabs(["➕ Single Entry", "📑 Bulk Queue", "📊 Monthly Report"])

with tab1:
    if kra_pin:
        # AI Scanner Section
        with st.expander("📸 AI Receipt Scanner", expanded=False):
            uploaded_doc = st.file_uploader("Upload Image/PDF", type=["pdf", "png", "jpg", "jpeg"])
            if uploaded_doc and st.button("🚀 Process with AI"):
                with st.spinner("Gemini is reading..."):
                    data = scan_receipt_with_ai(uploaded_doc)
                    if data:
                        st.session_state.scanned_total = float(data.get('total', 0.0))
                        st.session_state.scanned_pin = str(data.get('pin', "")).upper()
                        st.session_state.scanned_date = datetime.strptime(data.get('date'), '%Y-%m-%d').date() if data.get('date') else date.today()
                        st.json(data)
                        st.rerun()

        # Manual Form
        with st.form("transaction_form", clear_on_submit=True):
            t_type = st.selectbox("Category", ["Select Category","Sales (Output VAT)", "Purchase (Input VAT)"])
            col1, col2 = st.columns(2)
            
            with col1:
                date_val = st.session_state.get('scanned_date')
                date_str = st.text_input("Invoice Date", value=date_val.strftime('%Y/%m/%d') if date_val else "", placeholder="YYYY/MM/DD")
                amount = st.number_input("Amount (KES)", min_value=0.0, value=st.session_state.get('scanned_total', 0.0))
            
            with col2:
                other_pin = st.text_input("Counterparty PIN", value=st.session_state.get('scanned_pin', "")).upper()
                calc_mode = st.radio("Pricing Type", ["VAT Inclusive", "VAT Exclusive"], horizontal=True)

            # --- DYNAMIC CALCULATION PREVIEW ---
            if calc_mode == "VAT Inclusive":
                final_vat = amount - (amount / VAT_MULTIPLIER)
                final_total = amount
                final_net = amount / VAT_MULTIPLIER
            else:
                final_vat = amount * CURRENT_VAT_RATE
                final_total = amount + final_vat
                final_net = amount

            st.info(f"**Calculation Preview:** Net: {final_net:,.2f} | VAT: {final_vat:,.2f} | **Total: {final_total:,.2f}**")

            if st.form_submit_button("Save to Cloud"):
                try:
                    t_date = datetime.strptime(date_str.replace("-", "/"), '%Y/%m/%d').date()
                    sheet_name = "Sales" if "Sales" in t_type else "Purchases"
                    new_entry = pd.DataFrame([{
                        "ID": str(uuid.uuid4()),
                        "UserPIN": kra_pin, 
                        "Date": str(t_date), 
                        "CounterpartyPIN": other_pin, 
                        "Total": int(round(final_total)), 
                        "VAT": int(round(final_vat)),
                        "Timestamp": now_kenya.isoformat()
                    }])
                    conn.update(worksheet=sheet_name, data=pd.concat([conn.read(worksheet=sheet_name, ttl=0), new_entry], ignore_index=True))
                    st.success("✅ Saved Successfully!")
                    refresh_data()
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: Ensure Category is selected and Date is YYYY/MM/DD")

# [The Tab 2 and Tab 3 code remains largely the same as your primary app to maintain the PDF and Bulk features]
