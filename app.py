import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re

# --- GLOBAL CONFIGURATION (KRA Policy Changes) ---
# Change these values here to update the entire app instantly
CURRENT_VAT_RATE = 0.16  # 16% Standard Rate
VAT_MULTIPLIER = 1 + CURRENT_VAT_RATE # 1.16

# 1. Setup Page & Custom Styling
st.set_page_config(page_title="VAT Tracker Kenya", layout="wide", page_icon="🇰🇪")

# CSS to hide the +/- increment buttons and style containers
st.markdown("""
    <style>
    input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    .stMetric { background-color: #f0f2f6; padding: 15px; border-radius: 10px; border: 1px solid #d1d4dc; }
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
            st.warning("⚠️ PIN usually has 11 characters. Check if a digit is missing.")
        else:
            st.success("✅ PIN Format Verified")
    
    enable_vat_calc = st.toggle("Enable VAT Calculations", value=True)
    st.divider()
    st.info(f"Current VAT Rate: {CURRENT_VAT_RATE*100}%")
    
    # Deadline Countdown
    today = date.today()
    deadline = date(today.year, today.month, 20) if today.day <= 20 else date(today.year, today.month + 1, 20)
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
                        "Total": round(total), 
                        "VAT": round(vat), 
                        "eTIMS": "Yes" if is_etims else "No"
                    }])
                    conn.update(worksheet=sheet, data=pd.concat([existing, new_row], ignore_index=True))
                    st.success("✅ Saved Successfully!")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ Connection Error: {e}")

with tab2:
    st.subheader(f"Summary for KRA PIN: {kra_pin}")
    if not kra_pin:
        st.info("Enter your PIN in the sidebar to view reports.")
    else:
        # --- NEW PERIOD FILTER ---
        col_select, col_refresh = st.columns([3, 1])
        with col_select:
            # Users select a month and year to view
            report_date = st.date_input("Select Month to Review", value=date.today())
            filter_month = report_date.strftime("%Y-%m") # e.g. "2024-03"
        
        if st.button("Generate Report for " + report_date.strftime("%B %Y")):
            try:
                # Fetch Data
                sales_df = conn.read(worksheet="Sales", ttl=0)
                purch_df = conn.read(worksheet="Purchases", ttl=0)

                # Filter by PIN and the start of the Date string (Year-Month)
                u_sales = sales_df[(sales_df['UserPIN'] == kra_pin) & (sales_df['Date'].str.startswith(filter_month))]
                u_purch = purch_df[(purch_df['UserPIN'] == kra_pin) & (purch_df['Date'].str.startswith(filter_month))]

                # Summary Calculations
                out_vat = u_sales['VAT'].sum() if not u_sales.empty else 0
                in_vat = u_purch['VAT'].sum() if not u_purch.empty else 0
                net_vat = out_vat - in_vat

                # Dashboard Layout
                c1, c2, c3 = st.columns(3)
                c1.metric("Output VAT (Sales)", f"KES {out_vat:,.0f}")
                c2.metric("Input VAT (Purchases)", f"KES {in_vat:,.0f}")
                
                status = "PAYABLE" if net_vat > 0 else "CREDIT"
                c3.metric(f"VAT {status}", f"KES {abs(net_vat):,.0f}", 
                         delta="Payable" if net_vat > 0 else "Refundable", 
                         delta_color="inverse" if net_vat > 0 else "normal")

                st.divider()
                
                # Visual Chart
                chart_data = pd.DataFrame({"Amount": [out_vat, in_vat]}, index=["Sales VAT", "Purchase VAT"])
                st.bar_chart(chart_data)

                # Data Tables
                st.write(f"### Detailed Transactions for {report_date.strftime('%B %Y')}")
                st.write("**Sales**")
                st.dataframe(u_sales, use_container_width=True)
                st.write("**Purchases**")
                st.dataframe(u_purch, use_container_width=True)
                
            except Exception as e:
                st.error(f"Could not load report: {e}")
