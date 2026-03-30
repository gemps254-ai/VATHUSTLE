import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re

# 1. Setup Page & Custom Styling
st.set_page_config(page_title="VatHustle Kenya", layout="wide", page_icon="🇰🇪")

# CSS to hide the +/- increment buttons in number inputs
st.markdown("""
    <style>
    /* Hide spin buttons for Chrome, Safari, Edge, Opera */
    input::-webkit-outer-spin-button,
    input::-webkit-inner-spin-button {
        -webkit-appearance: none;
        margin: 0;
    }
    /* Hide spin buttons for Firefox */
    input[type=number] {
        -moz-appearance: textfield;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🇰🇪 VatHustle: SME VAT Tracker")

# 2. Connection & Auto-Initialization
conn = st.connection("gsheets", type=GSheetsConnection)

def init_sheets():
    """Ensures the required worksheets and headers exist in the linked Google Sheet."""
    headers = ["UserPIN", "Date", "CounterpartyPIN", "Total", "VAT", "eTIMS"]
    for sheet in ["Sales", "Purchases"]:
        try:
            # Attempt to read the sheet to check if it exists
            conn.read(worksheet=sheet, ttl="1d")
        except Exception:
            # If it fails, create the sheet with headers
            df = pd.DataFrame(columns=headers)
            conn.update(worksheet=sheet, data=df)

# Run initialization
init_sheets()

# 3. Sidebar: Business Profile & Deadline Countdown
with st.sidebar:
    st.header("Business Profile")
    
    # Requirement 4: Mandatory KRA PIN with validation
    kra_pin_raw = st.text_input("Your KRA PIN", placeholder="e.g., A012345678Z")
    kra_pin = kra_pin_raw.upper().strip()
    
    # Regex for KRA PIN: 1 Letter, 9 Digits, 1 Letter
    is_valid_pin = bool(re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin))
    
    if kra_pin and not is_valid_pin:
        st.error("Invalid PIN format. Must be 11 characters (e.g., A123456789Z).")
    
    enable_vat_calc = st.toggle("Enable VAT Calculations", value=True, help="Turn off if business is below VAT threshold")
    
    st.divider()
    
    # User Experience: Deadline Countdown
    today = date.today()
    # KRA Deadline is the
