import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re

# --- GLOBAL CONFIGURATION (KRA Policy Changes) ---
# Update this single value to change the tax rate across the entire app
CURRENT_VAT_RATE = 0.16  
VAT_MULTIPLIER = 1 + CURRENT_VAT_RATE 

# 1. Setup Page & Custom Styling
st.set_page_config(page_title="VAT Tracker Kenya", layout="wide", page_icon="🇰🇪")

# CSS to hide increment buttons and style the dashboard metrics
st.markdown("""
    <style>
    /* Hide spin buttons for all browsers */
    input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    
    /* Metric Card Styling */
    [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
    div[data-testid="metric-container"] {
        background-color: #f9f9f9;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🇰🇪 VAT Tracker")

# 2. Connection
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. Sidebar: Business Profile
with st.sidebar:
    st.header("Business Profile")
    kra_pin_raw = st.text_input("Your KRA PIN", placeholder="e.g., A012345678Z")
    kra_pin = kra_pin_raw.upper().strip()
    
    # Validation Logic
    is_valid_pin = bool(re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin))
    
    if kra_pin:
        if not is_valid_pin:
            st.warning("⚠️ PIN format usually has 11 characters (1 Letter, 9 Digits, 1 Letter).")
        else:
            st.success("✅ PIN Verified")
    
    enable_vat_calc = st.toggle("Enable VAT Calculations", value=True)
    st.divider()
    st.info(f"Current KRA VAT Rate: {int(CURRENT_VAT_RATE*100)}%")
    
    # Deadline Logic
    today = date.today()
    deadline_day = 20
    if today.day <= deadline_day:
        deadline = date(today.year, today.month, deadline_day)
    else:
        next_m = today.month + 1 if today.month < 12 else 1
        next_y = today.year if today.month < 12 else today.year + 1
        deadline = date(next_y, next_m, deadline_day)
    
    st.metric("Days to Filing Deadline", f"{(deadline - today).days} Days")
    st.caption("Deadline: 20th of every month")

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

            # Calculation using Global Constants
            if enable_vat_calc:
                if calc_mode == "VAT Inclusive":
                    net_val = amount / VAT_MULTIPLIER
                    vat_val = amount - net_val
                    total_to_save = amount
                else:
                    net_val = amount
                    vat_val = amount * CURRENT_VAT_RATE
                    total_to_save = net_val + vat_val
            else:
                vat_val, total_to_save = 0, amount

            if st.form_submit_button("Save to Cloud"):
                try:
                    sheet_name = "Sales" if "Sales" in t_type else "Purchases"
                    existing_data = conn.read(worksheet=sheet_name, ttl=0)
                    
                    new_entry = pd.DataFrame([{
                        "UserPIN": kra_pin, 
                        "Date": str(t_date), 
                        "CounterpartyPIN": other_pin, 
                        "Total": int(round(total_to_save)), 
                        "VAT": int(round(vat_val)), 
                        "eTIMS": "Yes" if is_etims else "No"
                    }])
                    
                    updated_df = pd.concat([existing_data, new_entry], ignore_index=True)
                    conn.update(worksheet=sheet_name, data=updated_df)
                    st.success(f"✅ Saved to {sheet_name}!")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ Error saving: {e}")

with tab2:
    st.subheader(f"Financial Summary: {kra_pin}")
    if not kra_pin:
        st.info("Enter your PIN in the sidebar to view reports.")
    else:
        # --- PERIOD SELECTOR (Month & Year Only) ---
        st.write("### Select Reporting Period")
        c_month, c_year = st.columns(2)
        
        list_months = ["January", "February", "March", "April", "May", "June", 
                       "July", "August", "September", "October", "November", "December"]
        
        with c_month:
            sel_month_name = st.selectbox("Month", list_months, index=date.today().month - 1)
            sel_month_num = list_months.index(sel_month_name) + 1
            
        with c_year:
            # Range from 2024 to next year
            sel_year = st.selectbox("Year", range(2024, date.today().year + 2), index=date.today().year - 2024)

        # Create filter string (e.g., "2026-03")
        filter_str = f"{sel_year}-{sel_month_num:02d}"

        if st.button(f"Generate Report for {sel_month_name} {sel_year}"):
            try:
                # Fetch Data
                sales_df = conn.read(worksheet="Sales", ttl=0)
                purch_df = conn.read(worksheet="Purchases", ttl=0)

                # Filter by PIN and the Month-Year prefix
                u_sales = sales_df[(sales_df['UserPIN'] == kra_pin) & (sales_df['Date'].str.startswith(filter_str))] if sales_df is not None else pd.DataFrame()
                u_purch = purch_df[(purch_df['UserPIN'] == kra_pin) & (purch_df['Date'].str.startswith(filter_str))] if purch_df is not None else pd.DataFrame()

                # Calculate Summaries
                out_vat = u_sales['VAT'].astype(float).sum() if not u_sales.empty else 0
                in_vat = u_purch['VAT'].astype(float).sum() if not u_purch.empty else 0
                net_vat = out_vat - in_vat

                # Dashboard Metrics
                m1, m2, m3 = st.columns(3)
                m1.metric("Output VAT (Sales)", f"KES {out_vat:,.0f}")
                m2.metric("Input VAT (Purchases)", f"KES {in_vat:,.0f}")
                
                label = "Payable" if net_vat >= 0 else "Credit"
                m3.metric(f"Net VAT {label}", f"KES {abs(net_vat):,.0f}", 
                          delta="Due to KRA" if net_vat > 0 else "Refundable",
                          delta_color="inverse" if net_vat > 0 else "normal")

                st.divider()

                # Detailed Tables
                st.write(f"### Transaction Records: {sel_month_name} {sel_year}")
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.write("**Sales Log**")
                    st.dataframe(u_sales[["Date", "CounterpartyPIN", "Total", "VAT"]].tail(10), use_container_width=True, hide_index=True)
                
                with col_right:
                    st.write("**Purchases Log**")
                    st.dataframe(u_purch[["Date", "CounterpartyPIN", "Total", "VAT"]].tail(10), use_container_width=True, hide_index=True)
                
            except Exception as e:
                st.error(f"Syntax or Connection Error: {e}")
