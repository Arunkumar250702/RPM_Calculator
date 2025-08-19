import re
import os
import io
import sqlite3
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
import pytesseract
import pandas as pd

# Ensure uploads folder exists
os.makedirs("uploads", exist_ok=True)

# SQLite DB setup
DB_FILE = "data.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS motor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    motor_name TEXT,
    date_time TEXT,
    power REAL,
    duty REAL,
    erpm REAL,
    i_batt REAL,
    i_motor REAL,
    t_fet REAL,
    t_motor REAL,
    volts_in REAL,
    normal_erpm REAL,
    rpm_48v REAL,
    image_url TEXT
)
""")
conn.commit()

app = FastAPI()

# Allow all CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static (placeholder only)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "ok", "message": "Backend is running"}

# OCR Extraction Endpoint
@app.post("/extract")
async def extract_data(file: UploadFile = File(...), motorName: str = Form(...)):
    image_data = await file.read()
    image = Image.open(io.BytesIO(image_data))
    text = pytesseract.image_to_string(image)

    def find_value(pattern):
        match = re.search(pattern, text, re.IGNORECASE)
        return float(match.group(1)) if match else None

    power = find_value(r"power\s*[:=]?\s*([\d\.]+)")
    duty = find_value(r"duty\s*[:=]?\s*([\d\.]+)")
    erpm = find_value(r"erpm\s*[:=]?\s*([\d\.]+)")
    i_batt = find_value(r"i\s*batt\s*[:=]?\s*([\d\.]+)")
    i_motor = find_value(r"i\s*motor\s*[:=]?\s*([\d\.]+)")
    t_fet = find_value(r"t\s*fet\s*[:=]?\s*([\d\.]+)")
    t_motor = find_value(r"t\s*motor\s*[:=]?\s*([\d\.]+)")
    volts_in = find_value(r"volts?\s*in\s*[:=]?\s*([\d\.]+)")

    normal_erpm = erpm / 7 if erpm else None
    rpm_48v = (erpm / 7 / volts_in * 48) if erpm and volts_in else None

    # Temporarily store image
    temp_path = os.path.join("uploads", f"temp_{file.filename}")
    with open(temp_path, "wb") as f:
        f.write(image_data)

    return {
        "Motor Name": motorName,
        "Power": power,
        "Duty": duty,
        "ERPM": erpm,
        "I Batt": i_batt,
        "I Motor": i_motor,
        "T FET": t_fet,
        "T Motor": t_motor,
        "Volts In": volts_in,
        "Normal ERPM": normal_erpm,
        "48V RPM": rpm_48v,
        "Temp Image": temp_path
    }

# Save to DB
@app.post("/save")
async def save_data(
    MotorName: str = Form(...),
    Power: float = Form(None),
    Duty: float = Form(None),
    ERPM: float = Form(None),
    IBatt: float = Form(None),
    IMotor: float = Form(None),
    TFET: float = Form(None),
    TMotor: float = Form(None),
    VoltsIn: float = Form(None),
    NormalERPM: float = Form(None),
    RPM48V: float = Form(None),
    TempImage: str = Form(...)
):
    # Save final image
    final_image_path = os.path.join("uploads", f"{MotorName}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    os.rename(TempImage, final_image_path)
    image_url = f"/{final_image_path}"

    # Insert into SQLite
    cursor.execute("""
        INSERT INTO motor_data (
            motor_name, date_time, power, duty, erpm, i_batt, i_motor, t_fet, t_motor, volts_in, normal_erpm, rpm_48v, image_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        MotorName,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        Power, Duty, ERPM, IBatt, IMotor, TFET, TMotor, VoltsIn, NormalERPM, RPM48V, image_url
    ))
    conn.commit()

    return {"status": "success", "message": "Data saved to DB", "image_url": image_url}

# Export DB to Excel
@app.get("/export")
async def export_excel():
    df = pd.read_sql_query("SELECT * FROM motor_data", conn)
    excel_file = "data.xlsx"
    df.to_excel(excel_file, index=False)
    return FileResponse(excel_file, filename="data.xlsx")
