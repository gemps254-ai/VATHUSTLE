import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re

# --- GLOBAL CONFIGURATION (KRA Policy Changes) ---
# Change these values here to update the entire app instantly
CURRENT_VAT_RATE = 0.16  # Current Standard Rate
VAT_MULTIPLIER = 1 + CURRENT_VAT_RATE 

# 1. Setup Page & Custom Styling
st.set_page_config(page_title="VAT Tracker Kenya", layout="wide", page_icon="🇰🇪")

# CSS to hide the +/- increment buttons and style metrics
st.markdown("""
    <style>
    input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    .stMetric { background-color: #f8f9fa; padding: 20px; border-radius: 8px; border: 1px solid #e9ecef; }
    </style>
""", unsafe_allow_html=True)

st.title("🇰🇪 VAT Tracker")

# 2. Connection
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. Sidebar
with st.sidebar:
    st.header("Business Profile")
    kra_pin_raw = st.text_input("Your KRA PIN", placeholder="e.g., A012345678Z")
    kra_pin = kra_pin_raw.upper().strip()
    
    is_valid_pin = bool(re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin))
    
    if kra_pin:
        if not is_valid_pin:
            st.warning("⚠️ PIN usually has 11 characters. Check for missing digits.")
        else:
            st.success("✅ PIN Format Verified")
    
    enable_vat_calc = st.toggle("Enable VAT Calculations", value=True)
    st.divider()
    st.info(f"Current VAT Rate: {int(CURRENT_VAT_RATE*100)}%")
    
    # Deadline Countdown
    today = date.today()
    deadline = date(today.year, today.month, 20) if today.today().day <= 20 else date(today.year, today.month + 1, 20)
    st.metric("Days to Filing Deadline", f"{(deadline - today).days} Days")

# 4. Main Interface
tab1, tab2 = st.tabs(["➕ Add Transaction", "📊 Monthly Report"])

with tab1:
    if not kra_pin:
        st.info("👋 Please enter your KRA PIN in the sidebar to start recording.")
    else:
        with st.form("transaction_form", clear_on_submit=True):
            st.subheader("Record New Entry")
            t_type = st.selectbox("Category", ["Sales (Output VAT)", "Purchase (Input VAT)"])
            
            col1, col2 = st.columns(2)
            with col1:
                t_date = st.date_input("Invoice Date", date.today())
                amount = st.number_input("Total Amount (KES)", min_value=0, step=1, format="%d")
            
            with col2:
                other_pin = st.text_input("Counterparty PIN").upper()
                is_etims = st.toggle("eTIMS Certified?", value=True)
                calc_mode = st.radio("Pricing Type", ["VAT Inclusive", "VAT Exclusive"], horizontal=True) if enable_vat_calc else "Exempt"

            # Logic using Global VAT Variables
            if enable_vat_calc:
                if calc_mode == "VAT Inclusive":
                    net = amount / VAT_MULTIPLIER
                    vat = amount - net
                    total = amount
                else:
                    net = amount
                    vat = amount * CURRENT_VAT_RATE
                    total = net + vat
            else:
                vat, total = 0, amount

            if st.form_submit_button("Save to Cloud"):
                try:
                    sheet = "Sales" if "Sales" in t_type else "Purchases"
                    existing = conn.read(worksheet=sheet, ttl=0)
                    new_row = pd.DataFrame([{
                        "UserPIN": kra_pin, 
                        "Date": str(t_date), 
                        "CounterpartyPIN": other_pin, 
                        "Total": int(round(total)), 
                        "VAT": int(round(vat)), 
                        "eTIMS": "Yes" if is_etims else "No"
                    }])
                    conn.update(worksheet=sheet, data=pd.concat([existing, new_row], ignore_index=True))
                    st.success("✅ Saved Successfully!")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ Connection Error: {e}")

with tab2:
    st.subheader(f"Financial Summary: {kra_pin}")
    if not kra_pin:
        st.info("Enter your PIN in the sidebar to view reports.")
    else:
        # --- REFINED MONTH & YEAR SELECTOR ---
        st.write("### Filter Reporting Period")
        c_month, c_year = st.columns(2)
        
        months = ["January", "February", "March", "April", "May", "June", 
                  "July", "August", "September", "October", "November", "December"]
        
        with c_month:
            sel_month_name = st.selectbox("Select Month", months, index=date.today().month - 1)
            sel_month_num = months.index(sel_month_name) + 1
            
        with c_year:
            # Range from 2024 to current year + 1
            sel_year = st.selectbox("Select Year", range(2024, date.today().year + 2), index=range(2024, date.today().year + 2).index(date.today().year))

        filter_period = f"{sel_year}-{sel_month_num:02d}" # Formats to "2026-03"

        if st.button(f"Generate Report for {sel_month_name} {sel_year}"):
            try:
                # Fetch Data
                sales_df = conn.read(worksheet="Sales", ttl=0)
                purch_df = conn.read(worksheet="Purchases", ttl=0)

                # Filter by PIN
