import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re

# 1. Setup Page & Custom Styling
st.set_page_config(page_title="VatHustle Kenya", layout="wide", page_icon="🇰🇪")

# Custom CSS to hide the spin buttons (up/down arrows) in the number input
st.markdown("""
    <style>
    input[type=number]::-webkit-inner-spin-button, 
    input[type=number]::-webkit-outer-spin-button { 
        -webkit-appearance: none; margin: 0; 
    }
    input[type=number] { -moz-appearance: textfield; }
    </style>
""", unsafe_allow_view_proxy=True)

st.title("🇰🇪 VatHustle: SME VAT Tracker")

# 2. Connection & Auto-Initialization
conn = st.connection("gsheets", type=GSheetsConnection)

def init_sheets():
    """Ensures the required worksheets and headers exist."""
    headers = ["UserPIN", "Date", "CounterpartyPIN", "Total", "VAT", "eTIMS"]
    for sheet in ["Sales", "Purchases"]:
        try:
            conn.read(worksheet=sheet, ttl=0)
        except:
            # If sheet doesn't exist, create an empty one with headers
            df = pd.DataFrame(columns=headers)
            conn.update(worksheet=sheet, data=df)

init_sheets()

# 3. Sidebar: Business Profile & Deadline Countdown
with st.sidebar:
    st.header("Business Profile")
    
    # KRA PIN Validation (Requirement 2)
    kra_pin = st.text_input("Your KRA PIN", placeholder="e.g., A012345678Z").upper().strip()
    
    is_valid_pin = bool(re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin))
    if kra_pin and not is_valid_pin:
        st.error("Invalid PIN format. Expected: 1 Letter, 9 Digits, 1 Letter.")
    
    enable_vat_calc = st.toggle("Enable VAT Calculations", value=True)
    
    st.divider()
    
    # Deadline Countdown (Experience Improvement)
    today = date.today()
    deadline = date(today.year, today.month, 20)
    if today.day > 20:
        # If past 20th, show next month's deadline
        if today.month == 12:
            deadline = date(today.year + 1, 1, 20)
        else:
            deadline = date(today.year, today.month + 1, 20)
    
    days_to_deadline = (deadline - today).days
    st.metric("Days to Filing Deadline", f"{days_to_deadline} Days")
    st.caption(f"Next KRA Deadline: {deadline.strftime('%d %b %Y')}")

# 4. Main Interface
tab1, tab2 = st.tabs(["➕ Add Transaction", "📊 Monthly Report"])

with tab1:
    if not is_valid_pin:
        st.info("👋 Welcome! Please enter a valid KRA PIN in the sidebar to begin.")
    else:
        st.subheader("Record New Entry")
        
        with st.form("transaction_form", clear_on_submit=True):
            t_type = st.selectbox("Category", ["Sales (Output VAT)", "Purchase (Input VAT)"])
            
            c1, c2 = st.columns(2)
            with c1:
                t_date = st.date_input("Invoice Date", date.today())
                # Requirement 5: No +/- buttons, manual entry only
                amount = st.number_input("Total Amount (KES)", min_value=0, step=1, value=0)
            
            with c2:
                other_pin = st.text_input("Counterparty PIN (Supplier/Buyer)").upper()
                is_etims = st.toggle("eTIMS Certified Invoice?", value=True)
                
                if enable_vat_calc:
                    calc_mode = st.radio("Pricing Structure", ["VAT Inclusive", "VAT Exclusive"], horizontal=True)
                else:
                    calc_mode = "Exempt"

            # VAT Calculation Logic
            if enable_vat_calc:
                if calc_mode == "VAT Inclusive":
                    net = amount / 1.16
                    vat = amount - net
                    total = amount
                else:
                    net = amount
                    vat = amount * 0.16
                    total = net + vat
            else:
                vat = 0
                total = amount

            vat = round(vat)
            total = round(total)

            # Warning for non-eTIMS or old invoices
            if not is_etims and "Purchase" in t_type:
                st.warning("⚠️ Non-eTIMS purchases may be rejected for Input VAT claims by KRA.")
            
            days_old = (date.today() - t_date).days
            if days_old > 180 and "Purchase" in t_type:
                st.error("❌ This invoice is over 6 months old and cannot be claimed.")
                submit = st.form_submit_button("Save Transaction", disabled=True)
            else:
                submit = st.form_submit_button("Save to Cloud")

            if submit:
                with st.spinner("Syncing with VatHustle Cloud..."):
                    sheet_name = "Sales" if "Sales" in t_type else "Purchases"
                    try:
                        existing = conn.read(worksheet=sheet_name, ttl=0)
                        new_data = pd.DataFrame([{
                            "UserPIN": kra_pin,
                            "Date": str(t_date),
                            "CounterpartyPIN": other_pin,
                            "Total": total,
                            "VAT": vat,
                            "eTIMS": "Yes" if is_etims else "No"
                        }])
                        updated = pd.concat([existing, new_data], ignore_index=True)
                        conn.update(worksheet=sheet_name, data=updated)
                        st.success(f"Transaction logged successfully in {sheet_name}!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Sync failed: {e}")

with tab2:
    if not is_valid_pin:
        st.info("Enter your PIN to view reports.")
    else:
        st.subheader(f"Performance Dashboard: {kra_pin}")
        
        if st.button("Fetch Latest Data"):
            try:
                # Requirement 3: Professional Report with Visuals
                s_df = conn.read(worksheet="Sales", ttl=0)
                p_df = conn.read(worksheet="Purchases", ttl=0)

                u_sales = s_df[s_df['UserPIN'] == kra_pin] if s_df is not None else pd.DataFrame()
                u_purch = p_df[p_df['UserPIN'] == kra_pin] if p_df is not None else pd.DataFrame()

                # Summary Metrics
                out_vat = u_sales['VAT'].sum() if not u_sales.empty else 0
                in_vat = u_purch['VAT'].sum() if not u_purch.empty else 0
                payable = out_vat - in_vat

                m1, m2, m3 = st.columns(3)
                m1.metric("Total Output VAT", f"KES {out_vat:,}")
                m2.metric("Total Input VAT", f"KES {in_vat:,}")
                m3.metric("Net VAT Payable", f"KES {payable:,}", delta="-Credit" if payable < 0 else "Payable")

                # Visual Chart
                if not u_sales.empty or not u_purch.empty:
                    st.write("### VAT Breakdown")
                    chart_data = pd.DataFrame({
                        "Category": ["Sales VAT", "Purchase VAT"],
                        "Amount": [out_vat, in_vat]
                    })
                    st.bar_chart(chart_data.set_index("Category"))

                st.divider()
                col_a, col_b = st.columns(2)
                with col_a:
                    st.write("**Recent Sales**")
                    st.table(u_sales.tail(5)[["Date", "Total", "VAT"]])
                with col_b:
                    st.write("**Recent Purchases**")
                    st.table(u_purch.tail(5)[["Date", "Total", "VAT"]])
                    
            except Exception as e:
                st.error("Data retrieval error. Ensure your Google Sheet headers match: UserPIN, Date, CounterpartyPIN, Total, VAT, eTIMS")
