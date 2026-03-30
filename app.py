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

# --- UPDATED SAVE LOGIC ---
    if st.button("Save to Cloud"):
        try:
            # 1. Pull existing data to see what's already there
            # We specify the worksheet name (make sure it matches your Google Sheet tab!)
            existing_data = conn.read(worksheet="Sales", ttl=0) 
        
            # 2. Create the new row as a small table
            new_row = pd.DataFrame([{
                "Date": str(t_date),
                "Type": t_type,
                "PIN": other_pin,
                "Total": amount,
                "VAT": round(vat_amount, 2),
                "eTIMS": "Yes" if is_etims else "No"
            }])

            # 3. Combine the old data with the new row
            updated_df = pd.concat([existing_data, new_row], ignore_index=True)

            # 4. Push the whole thing back to Google Sheets
            conn.update(worksheet="Sales", data=updated_df)
        
            st.success("✅ Transaction synced successfully to Google Sheets!")
            st.balloons()
        
        except Exception as e:
            st.error(f"❌ Error saving to Google Sheets: {e}")
            st.info("Check your 'Manage App > Logs' for the full error details.")
