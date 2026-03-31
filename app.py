import pytz
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re
import time
import io

from fpdf import FPDF

def get_recent_pins(pin_owner):
    try:
        s_df = conn.read(worksheet="Sales", ttl=0)
        p_df = conn.read(worksheet="Purchases", ttl=0)
        
        # Filter for this user's records only
        s_pins = s_df[s_df['UserPIN'] == pin_owner]['CounterpartyPIN'].tolist() if not s_df.empty else []
        p_pins = p_df[p_df['UserPIN'] == pin_owner]['CounterpartyPIN'].tolist() if not p_df.empty else []
        
        # Return unique, cleaned list of PINs
        return sorted(list(set(s_pins + p_pins)))
    except:
        return []

def create_full_vat_report(s_data, p_data, pin, period, o_v, i_v, n_v):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # --- HELPER TO CLEAN DATA (Prevents Unicode Errors) ---
    def clean_text(text):
        # Removes characters that Latin-1 (standard PDF fonts) cannot handle
        return str(text).encode('ascii', 'ignore').decode('ascii')
    
    # --- HEADER ---
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="GEMPS KE VAT Reconciliation Report", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    # Using clean_text just in case
    pdf.cell(200, 10, txt=clean_text(f"Generated on: {now_kenya.strftime('%d %b %Y %H:%M')}"), ln=True, align='C')
    pdf.ln(5)

    # --- BUSINESS & SUMMARY SECTION ---
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, clean_text(f" KRA PIN: {pin} | Period: {period}"), 1, 1, 'C', True)
    pdf.ln(10)

    # VAT Metrics Table
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(63, 10, "Output VAT (Sales)", 1, 0, 'C')
    pdf.cell(63, 10, "Input VAT (Purchases)", 1, 0, 'C')
    pdf.cell(64, 10, "Net VAT Payable/(Credit)", 1, 1, 'C')
    
    pdf.set_font("Arial", size=11)
    pdf.cell(63, 10, f"KES {o_v:,.2f}", 1, 0, 'C')
    pdf.cell(63, 10, f"KES {i_v:,.2f}", 1, 0, 'C')
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(64, 10, f"KES {n_v:,.2f}", 1, 1, 'C')
    pdf.ln(10)

    # --- HELPER TO BUILD TABLES ---
    def build_table(header_text, df):
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, header_text, 0, 1, 'C')
        
        pdf.set_fill_color(31, 119, 180) 
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(40, 8, "Date", 1, 0, 'C', True)
        pdf.cell(60, 8, "Counterparty PIN", 1, 0, 'C', True)
        pdf.cell(45, 8, "Total (KES)", 1, 0, 'C', True)
        pdf.cell(45, 8, "VAT (KES)", 1, 1, 'C', True)
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", size=9)
        if df.empty:
            pdf.cell(190, 8, "No records found.", 1, 1, 'C')
        else:
            for _, row in df.iterrows():
                # Clean the PIN and Date strings to avoid hidden Unicode characters
                pdf.cell(40, 8, clean_text(row['Date']), 1, 0, 'C')
                pdf.cell(60, 8, clean_text(row['CounterpartyPIN']), 1, 0, 'C')
                pdf.cell(45, 8, f"{row['Total']:,.2f}", 1, 0, 'C')
                pdf.cell(45, 8, f"{row['VAT']:,.2f}", 1, 1, 'C')
        pdf.ln(5)

    build_table("1. Sales Transactions (Output)", s_data)
    build_table("2. Purchase Transactions (Input)", p_data)

    # --- FOOTER (CRITICAL CHANGE HERE) ---
    pdf.set_y(-25)
    pdf.set_font("Arial", 'I', 8)
    # REMOVED the Emoji 🇰🇪 because standard FPDF Arial cannot render it
    footer_txt = "This is a computer-generated summary by GEMPS KE. Verify all figures with KRA eTIMS before filing."
    pdf.cell(0, 10, footer_txt, 0, 0, 'C')

    # --- RETURN (CRITICAL CHANGE HERE) ---
    # We output to a string, then convert that string to bytes
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- GLOBAL CONFIGURATION ---
CURRENT_VAT_RATE = 0.16  
VAT_MULTIPLIER = 1 + CURRENT_VAT_RATE 

# 1. Setup Page & Styling
st.set_page_config(page_title="GEMPS 🇰🇪 VAT Tracker", layout="wide", page_icon="🇰🇪")

# --- PHASE 2: MOBILE UI INJECTION ---
st.markdown("""
    <style>
    /* 1. Make Metrics look like Mobile Cards */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        color: #1f77b4;
    }
    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border: 2px solid #f0f2f6;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }

    /* 2. Optimize for Mobile Screens */
    @media (max-width: 640px) {
        .main .block-container {
            padding-top: 1rem;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        /* Make buttons larger for thumbs */
        .stButton>button {
            width: 100% !important;
            height: 3.5rem !important;
            font-size: 1.1rem !important;
            border-radius: 12px !important;
        }
    }

    /* 3. Hide the Sidebar on mobile to save space */
    @media (max-width: 640px) {
        [data-testid="stSidebar"] {
            display: none;
        }
    }
    </style>
""", unsafe_allow_html=True)

st.title("GEMPS 🇰🇪 VAT Tracker")

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
    
    st.header("🏢 GEMPS 🇰🇪")
    kra_pin_raw = st.text_input("Your KRA PIN", placeholder="e.g., A012345678Z")
    kra_pin = kra_pin_raw.upper().strip()
    
    is_valid_pin = bool(re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin))
    # Create a placeholder for messages
    msg = st.empty()

    if kra_pin:
        if not is_valid_pin:
            msg.warning("⚠️ Invalid PIN format.")
        else:
            msg.success("✅ PIN Verified")

            # Auto-disappear after 2 seconds
            time.sleep(2)
            msg.empty()
    st.divider() 
    
    enable_vat_calc = st.toggle("Enable VAT Calculations", value=True)

    
    # 1. Get current time specifically for Kenya
    kenya_tz = pytz.timezone('Africa/Nairobi')
    now_kenya = datetime.now(kenya_tz)
    today = now_kenya.date()

    # 2. Logic for the 20th of the month
    if today.day <= 20:
        deadline = date(today.year, today.month, 20)
    else:
        # If past the 20th, move to the 20th of next month
        if today.month == 12:
            deadline = date(today.year + 1, 1, 20)
        else:
            deadline = date(today.year, today.month + 1, 20)

    # 3. Calculate days remaining
    days_remaining = (deadline - today).days
    
    st.metric("Days to Next Deadline",f"{days_remaining} Days")
    st.caption(f"Current Date & Time: {now_kenya.strftime('%d %b %Y %H:%M')}")
    
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
                # NEW: Smart PIN Suggestions
                recent_pins = get_recent_pins(kra_pin)
                
                # If they have history, show a selectbox that allows new entries
                # If not, show the standard text input
                other_pin = st.selectbox(
                    "Counterparty PIN",
                    options=[""] + recent_pins + ["➕ New PIN..."],
                    index=0,
                    help="Select a recent partner or type 'New' to enter a fresh PIN."
                )

                if other_pin == "➕ New PIN...":
                    other_pin = st.text_input("Enter New PIN", value="").upper().strip()
                
                # Validation Guard
                if other_pin == kra_pin:
                    st.error("⚠️ Counterparty PIN cannot be your own PIN.")
                
                is_etims = st.toggle("eTIMS Certified?", value=True)
                
                # --- PHASE 2 PREVIEW ---
                st.button("📸 Scan Receipt (Coming Soon)", icon="📷", use_container_width=True, disabled=True)
                           
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
                if not other_pin or other_pin == kra_pin:
                    st.warning("Please provide a valid Counterparty PIN.")
                elif amount <= 0:
                    st.warning("Amount must be greater than 0.")
                else:
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

# --- TAB 2: BULK QUEUE (Integrated with Global VAT Toggle) ---
with tab2:
    if not kra_pin:
        st.info("👋 Enter KRA PIN in sidebar to start.")
    elif uploaded_file:
        try:
            # Read both sheets
            up_sales = pd.read_excel(uploaded_file, sheet_name='Sales', engine='openpyxl')
            up_purch = pd.read_excel(uploaded_file, sheet_name='Purchases', engine='openpyxl')
            
            def process_bulk(df, is_sale):
                if df.empty: return pd.DataFrame()
                processed = []
                for _, row in df.dropna(subset=['Amount']).iterrows():
                    amt = float(row['Amount'])
                    
                    # Logic: If toggle is OFF, VAT is always 0. 
                    # If toggle is ON, we look at the Excel row's VAT_Type.
                    if enable_vat_calc:
                        v_type = str(row['VAT_Type (Inclusive/Exclusive/Exempt)'])
                        if "Inclusive" in v_type:
                            v = amt - (amt / VAT_MULTIPLIER)
                            t = amt
                        elif "Exclusive" in v_type:
                            v = amt * CURRENT_VAT_RATE
                            t = amt + v
                        else: # Exempt
                            v, t = 0, amt
                    else:
                        v, t = 0, amt
                    
                    processed.append({
                        "UserPIN": kra_pin,
                        "Date": str(row['Date (YYYY-MM-DD)']).split(" ")[0],
                        "CounterpartyPIN": str(row['CounterpartyPIN']),
                        "Total": int(round(t)),
                        "VAT": int(round(v)),
                        "eTIMS": "Yes", 
                        "Category": "Sales" if is_sale else "Purchases"
                    })
                return pd.DataFrame(processed)

            # Combine processed data
            queue_df = pd.concat([process_bulk(up_sales, True), process_bulk(up_purch, False)], ignore_index=True)
            
            if not queue_df.empty:
                status_text = "VAT Calculations: ENABLED" if enable_vat_calc else "VAT Calculations: DISABLED (All VAT set to 0)"
                st.caption(f"✨ {status_text}")
                
                # Using Data Editor so you can delete/edit rows before pushing
                edited_df = st.data_editor(
                    queue_df, 
                    use_container_width=True, 
                    hide_index=True,
                    num_rows="dynamic",
                    column_config={
                        "Total": st.column_config.NumberColumn(format="KES %,d"),
                        "VAT": st.column_config.NumberColumn(format="KES %,d"),
                        "Category": st.column_config.SelectboxColumn(options=["Sales", "Purchases"])
                    }
                )
                
                c_btn1, = st.columns(1)
                if c_btn1.button("🚀 Push Queue to Cloud"):
                    with st.spinner("Uploading bulk data..."):
                        for s_type in ["Sales", "Purchases"]:
                            sub_df = edited_df[edited_df['Category'] == s_type].drop(columns=['Category'])
                            if not sub_df.empty:
                                existing = conn.read(worksheet=s_type, ttl=0)
                                conn.update(worksheet=s_type, data=pd.concat([existing, sub_df], ignore_index=True))
                        st.success("✅ Bulk Upload Complete!")
                        st.balloons()
            
            else:
                st.warning("The uploaded file appears to be empty.")
        except Exception as e:
            st.error(f"Excel Error: {e}")
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
                # 1. Initialize variables to 0 so they are ALWAYS defined
                o_v, i_v, n_v = 0.0, 0.0, 0.0
                
                s_df = conn.read(worksheet="Sales", ttl=0)
                p_df = conn.read(worksheet="Purchases", ttl=0)

                # 2. Process Sales Data
                if s_df is None or s_df.empty:
                    u_s = pd.DataFrame()
                else:
                    s_df['Date'] = s_df['Date'].astype(str)
                    u_s = s_df[(s_df['UserPIN'] == kra_pin) & (s_df['Date'].str.startswith(filter_str))]

                # 3. Process Purchases Data
                if p_df is None or p_df.empty:
                    u_p = pd.DataFrame()
                else:
                    p_df['Date'] = p_df['Date'].astype(str)
                    u_p = p_df[(p_df['UserPIN'] == kra_pin) & (p_df['Date'].str.startswith(filter_str))]

                # 4. Calculation Logic & Safety Check
                if (s_df is None or s_df.empty) and (p_df is None or p_df.empty):
                    st.warning(f"No transactions found for {sel_month_name} {sel_year}.")
                    st.session_state.report_data = None # Clear previous report if new search is empty
                else:
                    o_v = u_s['VAT'].astype(float).sum() if not u_s.empty else 0.0
                    i_v = u_p['VAT'].astype(float).sum() if not u_p.empty else 0.0
                    n_v = o_v - i_v

                    # Save to session state ONLY if there is data to show
                    st.session_state.report_data = {
                        "u_s": u_s, 
                        "u_p": u_p, 
                        "o_v": o_v, 
                        "i_v": i_v, 
                        "n_v": n_v, 
                        "period": f"{sel_month_name} {sel_year}"
                    }

            except Exception as e:
                st.error(f"Error generating report: {e}")

        # --- DISPLAY BLOCK (Handles Empty States Safely) ---
        if st.session_state.get("report_data"):
            rd = st.session_state.report_data
            
            # Show Metrics
            m1, m2, m3 = st.columns(3)
            m1.metric("Output VAT", f"KES {rd['o_v']:,.0f}")
            m2.metric("Input VAT", f"KES {rd['i_v']:,.0f}")
            m3.metric("Net VAT", f"KES {abs(rd['n_v']):,.0f}", delta="Due to KRA" if rd['n_v'] > 0 else "Credit")

            st.write("---")
            btn_col1, btn_col2, btn_col3 = st.columns(3)

            with btn_col1:
                if st.button("📄 Prepare Final PDF", use_container_width=True):
                    st.session_state.pdf_report_bytes = create_full_vat_report(
                        rd["u_s"], rd["u_p"], kra_pin, rd["period"], rd["o_v"], rd["i_v"], rd["n_v"]
                    )

            with btn_col2:
                # Only show download if bytes exist
                pdf_data = st.session_state.get("pdf_report_bytes")
                st.download_button(
                    label="📥 Download PDF",
                    data=pdf_data if pdf_data else b"",
                    file_name=f"VAT_Report_{rd['period']}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    disabled=not pdf_data
                )

            with btn_col3:
                if st.button("🔄 Clear Report", use_container_width=True):
                    st.session_state.report_data = None
                    st.session_state.pdf_report_bytes = None
                    st.rerun()

            st.divider()
            col_l, col_r = st.columns(2)
            cfg = {"Total": st.column_config.NumberColumn(format="KES %,d"), "VAT": st.column_config.NumberColumn(format="KES %,d")}
            
            with col_l:
                st.write("**Sales Log**")
                if not rd["u_s"].empty:
                    st.dataframe(rd["u_s"][["Date", "CounterpartyPIN", "Total", "VAT"]].tail(10), hide_index=True, column_config=cfg)
                else:
                    st.info("No sales records to display for this period.")

            with col_r:
                st.write("**Purchases Log**")
                if not rd["u_p"].empty:
                    st.dataframe(rd["u_p"][["Date", "CounterpartyPIN", "Total", "VAT"]].tail(10), hide_index=True, column_config=cfg)
                else:
                    st.info("No purchase records to display for this period.")
