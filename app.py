import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re
import io

# --- GLOBAL CONFIGURATION ---
CURRENT_VAT_RATE = 0.16  
VAT_MULTIPLIER = 1 + CURRENT_VAT_RATE 

# 1. Setup Page & Styling
st.set_page_config(page_title="VAT Tracker Kenya", layout="wide", page_icon="🇰🇪")

st.markdown("""
    <style>
    input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
    div[data-testid="metric-container"] { background-color: #f9f9f9; border: 1px solid #e0e0e0; padding: 15px; border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🇰🇪 VAT Tracker")

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

# 3. Sidebar: Business Profile & Bulk Features
with st.sidebar:
    
    st.header("Business Profile")
    kra_pin_raw = st.text_input("Your KRA PIN", placeholder="e.g., A012345678Z")
    kra_pin = kra_pin_raw.upper().strip()
    
    is_valid_pin = bool(re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin))
    if kra_pin:
        if not is_valid_pin: st.warning("⚠️ Invalid PIN format.")
        else: st.success("✅ PIN Verified")

    st.divider() 
    
    enable_vat_calc = st.toggle("Enable VAT Calculations", value=True)

    
    today = date.today()
    deadline = date(today.year, today.month, 20) if today.day <= 20 else date(today.year, today.month + 1, 20)
    st.metric("Days to Filing Deadline", f"{(deadline - today).days} Days")
    st.caption("Deadline: 20th of every month")
    
    st.divider()
    st.subheader("Bulk Upload")
    
    # Feature 1: Download Template
    template_data = generate_excel_template()
    st.download_button(
        label="Download Excel Template",
        data=template_data,
        file_name="BulkVAT_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    # Feature 2: Upload File
    uploaded_file = st.file_uploader("📤 Upload filled template", type=["xlsx"])
    
   
# 4. Main Interface
tab1, tab2, tab3 = st.tabs(["➕ Single Entry", "📑 Bulk Queue", "📊 Monthly Report"])

# --- TAB 1: SINGLE ENTRY (Your existing working code) ---
with tab1:
    if not kra_pin:
        st.info("👋 Enter KRA PIN in sidebar to start.")
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
                
                # Link to Sidebar Toggle
                if enable_vat_calc:
                    calc_mode = st.radio("Pricing Type", ["VAT Inclusive", "VAT Exclusive"], horizontal=True)
                else:
                    st.caption("VAT Calculation: **OFF**")
                    calc_mode = "Exempt"

            # Calculation Logic
            if enable_vat_calc:
                if calc_mode == "VAT Inclusive":
                    vat_val = amount - (amount / VAT_MULTIPLIER)
                    total_to_save = amount
                else:
                    vat_val = amount * CURRENT_VAT_RATE
                    total_to_save = amount + vat_val
            else:
                vat_val = 0
                total_to_save = amount

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
                    conn.update(worksheet=sheet_name, data=pd.concat([existing_data, new_entry], ignore_index=True))
                    st.success("✅ Saved!")
                except Exception as e:
                    st.error(f"Error: {e}")

# --- TAB 2: BULK QUEUE (New Feature) ---
with tab3: # Re-mapping Tab indices for clarity
    pass # Placeholder for Monthly Report logic below

with tab2:
    st.subheader("📋 Bulk Upload Queue")
    if not kra_pin:
        st.info("👋 Enter KRA PIN in sidebar to start.")
    elif uploaded_file:
        try:
            # Read both sheets
            up_sales = pd.read_excel(uploaded_file, sheet_name='Sales')
            up_purch = pd.read_excel(uploaded_file, sheet_name='Purchases')
            
            def process_bulk(df, is_sale):
                if df.empty: return pd.DataFrame()
                processed = []
                for _, row in df.iterrows():
                    amt = float(row['Amount'])
                    v_type = str(row['VAT_Type (Inclusive/Exclusive/Exempt)'])
                    
                    if "Inclusive" in v_type:
                        v = amt - (amt / VAT_MULTIPLIER)
                        t = amt
                    elif "Exclusive" in v_type:
                        v = amt * CURRENT_VAT_RATE
                        t = amt + v
                    else:
                        v, t = 0, amt
                    
                    processed.append({
                        "UserPIN": kra_pin,
                        "Date": str(row['Date (YYYY-MM-DD)']).split(" ")[0],
                        "CounterpartyPIN": str(row['CounterpartyPIN']),
                        "Total": int(round(t)),
                        "VAT": int(round(v)),
                        "eTIMS": "Yes", # Default for bulk
                        "Category": "Sales" if is_sale else "Purchases"
                    })
                return pd.DataFrame(processed)

            # Combine processed data
            queue_df = pd.concat([process_bulk(up_sales, True), process_bulk(up_purch, False)], ignore_index=True)
            
            if not queue_df.empty:
                st.write("Review the transactions below before pushing to Google Sheets:")
                st.dataframe(queue_df, use_container_width=True, hide_index=True, column_config={
                    "Total": st.column_config.NumberColumn(format="KES %,d"),
                    "VAT": st.column_config.NumberColumn(format="KES %,d")
                })
                
                c_btn1, c_btn2 = st.columns(2)
                if c_btn1.button("🚀 Push Queue to Cloud"):
                    with st.spinner("Uploading bulk data..."):
                        # Split back to Sales/Purchases for GSheet update
                        for s_type in ["Sales", "Purchases"]:
                            sub_df = queue_df[queue_df['Category'] == s_type].drop(columns=['Category'])
                            if not sub_df.empty:
                                existing = conn.read(worksheet=s_type, ttl=0)
                                conn.update(worksheet=s_type, data=pd.concat([existing, sub_df], ignore_index=True))
                        st.success("✅ Bulk Upload Complete!")
                
                if c_btn2.button("🗑️ Clear Queue"):
                    st.rerun()
            else:
                st.warning("The uploaded file is empty.")
        except Exception as e:
            st.error(f"Excel Error: Ensure you used the provided template. Detail: {e}")
    else:
        st.info("Upload an Excel file in the sidebar to see the queue here.")

# --- TAB 3: MONTHLY REPORT (Your existing working code) ---
with tab3:
    st.subheader(f"VAT Summary: {kra_pin}")
    if not kra_pin:
        st.info("👋 Enter KRA PIN in sidebar to start.")
    else:
        c_month, c_year = st.columns(2)
        list_months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        with c_month:
            sel_month_name = st.selectbox("Month", list_months, index=date.today().month - 1)
            sel_month_num = list_months.index(sel_month_name) + 1
        with c_year:
            sel_year = st.selectbox("Year", range(2024, date.today().year + 2), index=date.today().year - 2024)

        filter_str = f"{sel_year}-{sel_month_num:02d}"

        if st.button(f"Generate Report for {sel_month_name} {sel_year}"):
            try:
                s_df = conn.read(worksheet="Sales", ttl=0)
                p_df = conn.read(worksheet="Purchases", ttl=0)
                u_s = s_df[(s_df['UserPIN'] == kra_pin) & (s_df['Date'].str.startswith(filter_str))] if s_df is not None else pd.DataFrame()
                u_p = p_df[(p_df['UserPIN'] == kra_pin) & (p_df['Date'].str.startswith(filter_str))] if p_df is not None else pd.DataFrame()

                o_v = u_s['VAT'].astype(float).sum() if not u_s.empty else 0
                i_v = u_p['VAT'].astype(float).sum() if not u_p.empty else 0
                n_v = o_v - i_v

                m1, m2, m3 = st.columns(3)
                m1.metric("Output VAT", f"KES {o_v:,.0f}")
                m2.metric("Input VAT", f"KES {i_v:,.0f}")
                m3.metric("Net VAT", f"KES {abs(n_v):,.0f}", delta="Due to KRA" if n_v > 0 else "Credit")

                st.divider()
                st.write("**Recent Records**")            
                col_l, col_r = st.columns(2)
                curr_cfg = {"Total": st.column_config.NumberColumn(format="KES %,d"), "VAT": st.column_config.NumberColumn(format="KES %,d")}
                with col_l:
                    st.write("**Sales Log**")
                    st.dataframe(u_s[["Date", "CounterpartyPIN", "Total", "VAT"]].tail(10), hide_index=True, column_config=curr_cfg)
                with col_r:
                    st.write("**Purchases Log**")
                    st.dataframe(u_p[["Date", "CounterpartyPIN", "Total", "VAT"]].tail(10), hide_index=True, column_config=curr_cfg)
            except Exception as e:
                st.error(f"Error: {e}")
