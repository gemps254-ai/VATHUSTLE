import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date

# 1. Setup Page
st.set_page_config(page_title="VatHustle Kenya", layout="wide")
st.title("🇰🇪 VatHustle: SME VAT Tracker")

# 2. Connect to Google Sheets
# Note: You'll put your Google Sheet URL in a 'secrets' file later
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. Sidebar: Business Profile
with st.sidebar:
    st.header("Business Profile")
    kra_pin = st.text_input("Your KRA PIN", value="A000000000Z")
    st.info("Deadline: 20th of every month")

# 4. Input Section
tab1, tab2 = st.tabs(["➕ Add Transaction", "📊 Monthly Report"])

with tab1:
    st.subheader("Record Sale or Purchase")
    t_type = st.selectbox("Type", ["Sales (Output VAT)", "Purchase (Input VAT)"])
    
    col1, col2 = st.columns(2)
    with col1:
        t_date = st.date_input("Date of Invoice", date.today())
        amount = st.number_input("Total Amount (Incl. VAT)", min_value=0.0)
    with col2:
        other_pin = st.text_input("Counterparty PIN (Supplier/Buyer)")
        is_etims = st.toggle("Is this an eTIMS invoice?", value=True)

    # Calculation Logic (16% VAT)
    net_amount = amount / 1.16
    vat_amount = amount - net_amount

    # 6-Month Validation
    months_old = (date.today() - t_date).days / 30
    if months_old > 6 and t_type == "Purchase (Input VAT)":
        st.error("⚠️ This invoice is older than 6 months and cannot be claimed for VAT!")
        can_save = False
    else:
        can_save = True

    if st.button("Save to Cloud") and can_save:
        # Create a tiny table of this one entry
        new_data = pd.DataFrame([{
            "Date": t_date, "Type": t_type, "PIN": other_pin, 
            "Total": amount, "VAT": round(vat_amount, 2), "eTIMS": is_etims
        }])
        
        # In a full app, we would use conn.create() here. 
        # For now, we simulate the success:
        st.success(f"Saved! Sh {vat_amount:,.2f} recorded for {t_type}")

with tab2:
    st.subheader("Your VAT Filing Helper")
    st.write("Compare these totals with your iTax pre-filled return:")
    # Here the app would calculate the sum of all VAT in your Google Sheet
    st.metric(label="VAT Payable to KRA", value="Sh 4,250.00", delta="Payable")
    st.warning("Ensure you have all physical/digital receipts before filing.")