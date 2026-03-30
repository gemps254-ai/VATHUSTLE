import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re
import io

# --- GLOBAL CONFIGURATION ---
CURRENT_VAT_RATE = 0.16  
VAT_MULTIPLIER = 1 + CURRENT_VAT_RATE 

# 1. Setup Page & ADVANCED Custom Styling
st.set_page_config(page_title="VatHustle Kenya", layout="wide", page_icon="🇰🇪")

st.markdown("""
    <style>
    /* Main Background Gradient */
    .stApp {
        background: linear-gradient(to right, #ece9e6, #ffffff);
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #0e1117 !important;
    }
    
    /* Metric Card Styling */
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 800; color: #1f77b4; }
    div[data-testid="metric-container"] {
        background-color: white;
        border: 1px solid #e6e9ef;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Input Styling */
    input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    </style>
""", unsafe_allow_html=True)

st.title("🇰🇪 VatHustle")

# 2. Connection
conn = st.connection("gsheets", type=GSheetsConnection)

# --- HELPER: TEMPLATE GENERATOR ---
def generate_excel_template():
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        cols = ["Date (YYYY-MM-DD)", "CounterpartyPIN", "Amount", "VAT_Type (Inclusive/Exclusive/Exempt)"]
        pd.DataFrame(columns=cols).to_excel(writer, sheet_name='Sales', index=False)
        pd.DataFrame(columns=cols).to_excel(writer, sheet_name='Purchases', index=False)
    return output.getvalue()

# 3. Sidebar
with st.sidebar:
    st.header("🏢 Business Profile")
    kra_pin_raw = st.text_input("KRA PIN", placeholder="A012345678Z")
    kra_pin = kra_pin_raw.upper().strip()
    
    is_valid_pin = bool(re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin))
    if kra_pin:
        if not is_valid_pin: st.warning("⚠️ Invalid Format")
        else: st.success("✅ PIN Verified")

    st.divider()
    enable_vat_calc = st.toggle("Enable Tax Logic", value=True)
    
    # Filing Countdown
    today = date.today()
    deadline = date(today.year, today.month, 20) if today.day <= 20 else date(today.year, (today.month % 12) + 1, 20)
    st.metric("Days to Filing", f"{(deadline - today).days}")
    
    st.divider()
    st.subheader("📤 Bulk Upload")
    template_data = generate_excel_template()
    st.download_button("📥 Download Template", data=template_data, file_name="VatHustle_Template.xlsx")
    uploaded_file = st.file_uploader("Upload XLSX", type=["xlsx"])

# 4. Main Interface
tab1, tab2, tab3 = st.tabs(["➕ Single Entry", "📑 Bulk Queue", "📊 Reports"])

with tab1:
    if not kra_pin:
        st.info("👋 Please enter your PIN in the sidebar.")
    else:
        with st.form("single_entry", clear_on_submit=True):
            st.subheader("New Transaction")
            col1, col2 = st.columns(2)
            with col1:
                t_type = st.selectbox("Type", ["Sales (Output)", "Purchases (Input)"])
                t_date = st.date_input("Date", date.today())
                amount = st.number_input("Total Amount", min_value=0, step=1)
            with col2:
                other_pin = st.text_input("Counterparty PIN").upper()
                calc_mode = st.radio("VAT Treatment", ["VAT Inclusive", "VAT Exclusive"]) if enable_vat_calc else "Exempt"

            if st.form_submit_button("Submit Transaction"):
                # Logic
                if enable_vat_calc:
                    v = amount - (amount/VAT_MULTIPLIER) if calc_mode == "VAT Inclusive" else amount * CURRENT_VAT_RATE
                    t = amount if calc_mode == "VAT Inclusive" else amount + v
                else: v, t = 0, amount
                
                sheet = "Sales" if "Sales" in t_type else "Purchases"
                existing = conn.read(worksheet=sheet, ttl=0)
                new_row = pd.DataFrame([{"UserPIN": kra_pin, "Date": str(t_date), "CounterpartyPIN": other_pin, "Total": int(round(t)), "VAT": int(round(v)), "eTIMS": "Yes"}])
                conn.update(worksheet=sheet, data=pd.concat([existing, new_row], ignore_index=True))
                st.success("Transaction Logged!")

with tab2:
    st.subheader("📑 Bulk Transaction Queue")
    if not kra_pin:
        st.info("Enter PIN to access queue.")
    elif uploaded_file:
        try:
            up_s = pd.read_excel(uploaded_file, sheet_name='Sales', engine='openpyxl')
            up_p = pd.read_excel(uploaded_file, sheet_name='Purchases', engine='openpyxl')
            
            def process(df, is_sale):
                if df.empty: return pd.DataFrame()
                data = []
                for _, r in df.dropna(subset=['Amount']).iterrows():
                    amt = float(r['Amount'])
                    if enable_vat_calc:
                        vt = str(r['VAT_Type (Inclusive/Exclusive/Exempt)'])
                        v = amt - (amt/VAT_MULTIPLIER) if "Inclusive" in vt else (amt * CURRENT_VAT_RATE if "Exclusive" in vt else 0)
                        t = amt if "Inclusive" in vt else (amt + v if "Exclusive" in vt else amt)
                    else: v, t = 0, amt
                    data.append({"UserPIN": kra_pin, "Date": str(r['Date (YYYY-MM-DD)']).split(" ")[0], "CounterpartyPIN": str(r['CounterpartyPIN']), "Total": int(round(t)), "VAT": int(round(v)), "Category": "Sales" if is_sale else "Purchases"})
                return pd.DataFrame(data)

            queue = pd.concat([process(up_s, True), process(up_p, False)], ignore_index=True)
            
            if not queue.empty:
                st.write("Review & Edit Staged Transactions:")
                # Use Data Editor for "Delete/Edit" functionality
                final_df = st.data_editor(queue, use_container_width=True, hide_index=True, num_rows="dynamic")
                
                if st.button("🚀 Confirm & Upload All"):
                    for s in ["Sales", "Purchases"]:
                        sub = final_df[final_df['Category'] == s].drop(columns=['Category'])
                        if not sub.empty:
                            ex = conn.read(worksheet=s, ttl=0)
                            conn.update(worksheet=s, data=pd.concat([ex, sub], ignore_index=True))
                    st.success("Cloud Sync Complete!")
            else: st.warning("File is empty.")
        except Exception as e: st.error(f"Error: {e}")
    else: st.info("Upload XLSX in sidebar to stage transactions.")

with tab3:
    # Monthly Report Logic (Same as before)
    if not kra_pin: st.info("Enter PIN.")
    else:
        # Period Selectors
        c1, c2 = st.columns(2)
        with c1: month = st.selectbox("Month", ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], index=date.today().month-1)
        with c2: year = st.selectbox("Year", [2025, 2026])
        
        if st.button("Generate Report"):
            # Filtering and Metrics...
            st.write(f"Displaying data for {month} {year}...")
            # (Insert your metric and table logic here)
