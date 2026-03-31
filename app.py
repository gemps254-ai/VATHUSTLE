import pytz
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import re
import time
import io
from fpdf import FPDF
import google.generativeai as genai
import json
import uuid
import pytesseract
from PIL import Image

# ------------------ CONFIG ------------------
st.set_page_config(page_title="GEMPS VAT Tracker 🇰🇪", layout="wide")

kenya_tz = pytz.timezone('Africa/Nairobi')
now_kenya = datetime.now(kenya_tz)

CURRENT_VAT_RATE = 0.16
VAT_MULTIPLIER = 1 + CURRENT_VAT_RATE

# ------------------ GEMINI ------------------
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# ------------------ CONNECTION ------------------
conn = st.connection("gsheets", type=GSheetsConnection)

# ------------------ CACHE ------------------
@st.cache_data(ttl=600)
def load_data(sheet):
    return conn.read(worksheet=sheet)

def refresh_data():
    st.cache_data.clear()

# ------------------ OCR ------------------
def extract_text_from_image(uploaded_file):
    try:
        image = Image.open(uploaded_file)
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        st.error(f"OCR Error: {e}")
        return ""

# ------------------ AI SCANNER ------------------
def scan_receipt_with_ai(uploaded_file):
    model = genai.GenerativeModel('gemini-1.5-flash')

    try:
        ocr_text = extract_text_from_image(uploaded_file)

        if not ocr_text.strip():
            st.error("No readable text found.")
            return None

        prompt = f"""
        Extract:
        date (YYYY-MM-DD)
        total (number)
        pin (KRA PIN)
        vat (number)

        TEXT:
        {ocr_text}

        Return JSON only.
        """

        response = model.generate_content(prompt)
        clean_json = re.sub(r'```json|```', '', response.text).strip()

        return json.loads(clean_json)

    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# ------------------ PDF ------------------
def create_pdf(sales, purchases, pin, period, ov, iv, nv):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, f"VAT Report - {period}", ln=True)
    pdf.cell(200, 10, f"KRA PIN: {pin}", ln=True)

    pdf.ln(5)
    pdf.cell(200, 10, f"Output VAT: {ov}", ln=True)
    pdf.cell(200, 10, f"Input VAT: {iv}", ln=True)
    pdf.cell(200, 10, f"Net VAT: {nv}", ln=True)

    return pdf.output(dest='S').encode('latin-1')

# ------------------ SIDEBAR ------------------
with st.sidebar:
    st.header("GEMPS 🇰🇪")

    kra_pin = st.text_input("KRA PIN").upper().strip()

    if kra_pin:
        if not re.match(r"^[A-Z]\d{9}[A-Z]$", kra_pin):
            st.warning("Invalid PIN")
        else:
            st.success("PIN Verified")

    if st.button("🔄 Refresh"):
        refresh_data()

# ------------------ MAIN ------------------
st.title("VAT Tracker 🇰🇪")

if not kra_pin:
    st.info("Enter your KRA PIN to continue.")
    st.stop()

sales = load_data("Sales")
purchases = load_data("Purchases")

# ------------------ DASHBOARD ------------------
current_month = now_kenya.strftime('%Y-%m')

s = sales[(sales['UserPIN'] == kra_pin) & (sales['Date'].str.startswith(current_month))]
p = purchases[(purchases['UserPIN'] == kra_pin) & (purchases['Date'].str.startswith(current_month))]

ov = s['VAT'].astype(float).sum() if not s.empty else 0
iv = p['VAT'].astype(float).sum() if not p.empty else 0
nv = ov - iv

c1, c2, c3 = st.columns(3)
c1.metric("Sales VAT", f"KES {ov:,.0f}")
c2.metric("Purchase VAT", f"KES {iv:,.0f}")
c3.metric("Net VAT", f"KES {nv:,.0f}")

# ------------------ CHART ------------------
if not s.empty:
    st.subheader("VAT Trend")
    chart = s.groupby('Date')['VAT'].sum()
    st.line_chart(chart)

# ------------------ SCANNER ------------------
st.subheader("📸 Scan Receipt")

uploaded = st.file_uploader("Upload receipt", type=["jpg","png","jpeg"])

if uploaded:
    if st.button("Scan"):
        data = scan_receipt_with_ai(uploaded)
        if data:
            st.success("Extracted!")
            st.json(data)

# ------------------ FORM ------------------
st.subheader("Add Transaction")

date_input = st.text_input("Date (YYYY/MM/DD)")
amount = st.number_input("Amount", min_value=0.0)

counterparty = st.text_input("Counterparty PIN").upper()

calc_mode = st.radio("VAT Mode", ["Inclusive", "Exclusive"])

if calc_mode == "Inclusive":
    vat = amount - (amount / VAT_MULTIPLIER)
    total = amount
else:
    vat = amount * CURRENT_VAT_RATE
    total = amount + vat

st.info(f"""
Net: {total - vat:.2f}
VAT: {vat:.2f}
Total: {total:.2f}
""")

if st.button("Save"):
    try:
        t_date = datetime.strptime(date_input.replace("-", "/"), "%Y/%m/%d")

        if not re.match(r"^[A-Z]\d{9}[A-Z]$", counterparty):
            st.error("Invalid counterparty PIN")
            st.stop()

        new = pd.DataFrame([{
            "ID": str(uuid.uuid4()),
            "Timestamp": now_kenya.isoformat(),
            "UserPIN": kra_pin,
            "Date": str(t_date.date()),
            "CounterpartyPIN": counterparty,
            "Total": int(total),
            "VAT": int(vat)
        }])

        existing = load_data("Sales")
        conn.update(worksheet="Sales", data=pd.concat([existing, new], ignore_index=True))

        msg = st.empty()
        msg.success("Saved!")
        time.sleep(2)
        msg.empty()

    except Exception as e:
        st.error(e)
