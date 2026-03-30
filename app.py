import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re

# 1. Setup Page & Custom Styling
st.set_page_config(page_title="VatHustle Kenya", layout="wide", page_icon="🇰🇪")

# CSS to hide the +/- increment buttons
st.markdown("""
    <style>
    input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    </style>
""", unsafe_allow_html=True)

st.title("🇰🇪 VatHustle: SME VAT Tracker")

# 2. Connection
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. Sidebar
with st.sidebar:
    st.header("Business Profile")
    kra_pin_raw = st.text_input("Your KRA PIN", placeholder="e.g., A012345678Z")
    kra_pin = kra_pin_raw.upper().strip()
    
    # Check if PIN is valid (Standard is 11 chars: 1 Letter, 9 Digits, 1 Letter)
    is_valid_pin = bool(re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin))
    
    if kra_pin:
        if not is_valid_pin:
            st.warning("⚠️ PIN usually has 11 characters. Check if a digit is missing.")
        else:
            st.success("✅ PIN Format Verified")
    
    enable_vat_calc = st.toggle("Enable VAT Calculations", value=True)
    st.divider()
    
    # Deadline Countdown
    today = date.today()
    deadline = date(today.year, today.month, 20) if today.day <= 20 else date(today.year, today.month + 1, 20)
    st.metric("Days to Filing", f"{(deadline - today).days} Days")

# 4. Main Interface - UNLOCKED
# We remove the "if not is_valid_pin" gate so the app is never blank
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
                calc_mode = st.radio("Type", ["VAT Inclusive", "VAT Exclusive"], horizontal=True) if enable_vat_calc else "Exempt"

            # Calculation Logic
            if enable_vat_calc:
                vat = (amount - (amount / 1.16)) if calc_mode == "VAT Inclusive" else (amount * 0.16)
                total = amount if calc_mode == "VAT Inclusive" else (amount * 1.16)
            else:
                vat, total = 0, amount

            if st.form_submit_button("Save to Cloud"):
                try:
                    sheet = "Sales" if "Sales" in t_type else "Purchases"
                    existing = conn.read(worksheet=sheet, ttl=0)
                    new_row = pd.DataFrame([{"UserPIN": kra_pin, "Date": str(t_date), "CounterpartyPIN": other_pin, "Total": round(total), "VAT": round(vat), "eTIMS": "Yes" if is_etims else "No"}])
                    conn.update(worksheet=sheet, data=pd.concat([existing, new_row], ignore_index=True))
                    st.success("Saved!")
                    st.balloons()
                except Exception as e:
                    st.error(f"Error: {e}")

with tab2:
    if not kra_pin:
        st.info("Enter your PIN to view reports.")
    else:
        if st.button("Refresh Report"):
            try:
                s_df = conn.read(worksheet="Sales", ttl=0)
                p_df = conn.read(worksheet="Purchases", ttl=0)
                u_s = s_df[s_df['UserPIN'] == kra_pin] if s_df is not None else pd.DataFrame()
                u_p = p_df[p_df['UserPIN'] == kra_pin] if p_df is not None else pd.DataFrame()
                
                out_v = u_s['VAT'].sum() if not u_s.empty else 0
                in_v = u_p['VAT'].sum() if not u_p.empty else 0
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Output VAT", f"{out_v:,}")
                c2.metric("Input VAT", f"{in_v:,}")
                c3.metric("Net Position", f"{out_v - in_v:,}")
                st.bar_chart(pd.DataFrame({"VAT": [out_v, in_v]}, index=["Sales", "Purchases"]))
            except:
                st.error("Could not fetch data.")
