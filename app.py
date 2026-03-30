import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date

# 1. Setup Page
st.set_page_config(page_title="VatHustle Kenya", layout="wide")
st.title("🇰🇪 VatHustle: SME VAT Tracker")

# 2. Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. Sidebar: Business Profile
with st.sidebar:
    st.header("Business Profile")
    # Requirement 4: Mandatory KRA PIN & User isolation
    kra_pin = st.text_input("Your KRA PIN", placeholder="e.g., A012345678Z")
    
    # Requirement 1: Global VAT Toggle (Master Switch)
    enable_vat_calc = st.toggle("Enable VAT Calculations", value=True, help="Turn off if business is below VAT threshold")
    
    st.info("Deadline: 20th of every month")

# 4. Input Section
tab1, tab2 = st.tabs(["➕ Add Transaction", "📊 Monthly Report"])

with tab1:
    st.subheader("Record Sale or Purchase")
    
    # Check for PIN before allowing entry
    if not kra_pin:
        st.warning("Please enter your KRA PIN in the sidebar to start recording transactions.")
    else:
        t_type = st.selectbox("Transaction Category", ["Sales (Output VAT)", "Purchase (Input VAT)"])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            # Requirement 6: Date picker with full navigation
            t_date = st.date_input("Date of Invoice", date.today(), help="Select date from calendar")
            
            # Requirement 5: Manual entry only, no +/- buttons, integers only
            amount = st.number_input("Amount", min_value=0, step=1, format="%d")
            
        with col2:
            other_pin = st.text_input("Counterparty PIN")
            
            # Requirement 1: Inline Toggle for Inclusive/Exclusive
            calc_type = "Inclusive"
            if enable_vat_calc:
                calc_type = st.radio("Pricing Type", ["VAT Inclusive", "VAT Exclusive"], horizontal=True)

        with col3:
            is_etims = st.toggle("eTIMS Invoice?", value=True)

        # Requirement 1 & 5: Logic for VAT Calculation
        if enable_vat_calc:
            if calc_type == "VAT Inclusive":
                net_amount = amount / 1.16
                vat_amount = amount - net_amount
                total_display = amount
            else:
                net_amount = amount
                vat_amount = amount * 0.16
                total_display = net_amount + vat_amount
        else:
            net_amount = amount
            vat_amount = 0
            total_display = amount

        # Rounding to nearest whole number as requested
        vat_amount = round(vat_amount)
        total_display = round(total_display)

        st.metric("VAT to Record", f"KES {vat_amount:,}")

        # 6-Month Validation
        days_old = (date.today() - t_date).days
        can_save = True
        if days_old > 180 and "Purchase" in t_type:
            st.error("⚠️ This purchase is older than 6 months and cannot be claimed!")
            can_save = False

        if st.button("Save to Cloud") and can_save:
            try:
                # Requirement 2: Route to correct worksheet
                sheet_name = "Sales" if "Sales" in t_type else "Purchases"
                
                existing_data = conn.read(worksheet=sheet_name, ttl=0)
                
                # Requirement 4: Added 'UserPIN' to the row to prevent data mixing
                new_row = pd.DataFrame([{
                    "UserPIN": kra_pin,
                    "Date": str(t_date),
                    "CounterpartyPIN": other_pin,
                    "Total": total_display,
                    "VAT": vat_amount,
                    "eTIMS": "Yes" if is_etims else "No"
                }])

                if existing_data is not None and not existing_data.empty:
                    updated_df = pd.concat([existing_data, new_row], ignore_index=True)
                else:
                    updated_df = new_row

                conn.update(worksheet=sheet_name, data=updated_df)
                st.success(f"✅ Synced to {sheet_name} worksheet!")
                st.balloons()
                
            except Exception as e:
                st.error(f"❌ Connection Error: {e}")

with tab2:
    # Requirement 3: Reforming the Monthly Report
    st.subheader(f"Financial Summary for PIN: {kra_pin}")
    if not kra_pin:
        st.info("Enter your PIN to view your reports.")
    else:
        if st.button("Refresh Report"):
            try:
                # Fetch both sheets
                sales_df = conn.read(worksheet="Sales", ttl=0)
                purch_df = conn.read(worksheet="Purchases", ttl=0)

                # Filter for THIS user only (Requirement 4 isolation)
                user_sales = sales_df[sales_df['UserPIN'] == kra_pin] if sales_df is not None else pd.DataFrame()
                user_purch = purch_df[purch_df['UserPIN'] == kra_pin] if purch_df is not None else pd.DataFrame()

                # Visual Summary
                c1, c2, c3 = st.columns(3)
                out_vat = user_sales['VAT'].sum() if not user_sales.empty else 0
                in_vat = user_purch['VAT'].sum() if not user_purch.empty else 0
                
                c1.metric("Output VAT (Sales)", f"KES {out_vat:,.0f}")
                c2.metric("Input VAT (Purchases)", f"KES {in_vat:,.0f}")
                c3.metric("VAT Payable/Credit", f"KES {(out_vat - in_vat):,.0f}", delta_color="inverse")

                st.divider()
                st.write("### Recent Sales")
                st.dataframe(user_sales.tail(5), use_container_width=True)
                
                st.write("### Recent Purchases")
                st.dataframe(user_purch.tail(5), use_container_width=True)
            except:
                st.error("Could not retrieve data. Ensure 'UserPIN' column exists in your Google Sheets.")
