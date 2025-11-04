import os
import io
import re
import sqlite3
import platform
import subprocess
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
import pytesseract
import pandas as pd
import traceback


# =========================================================
# ✅ Check Tesseract Installation
# =========================================================
TESSERACT_AVAILABLE = True
try:
    result = subprocess.run(["tesseract", "--version"], capture_output=True, text=True)
    print("✅ Tesseract found:", result.stdout.split("\n")[0])
except Exception as e:
    print("❌ Tesseract not found:", str(e))
    TESSERACT_AVAILABLE = False

# Windows-specific path (for local testing)
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# On Render (Linux) → tesseract path = /usr/bin/tesseract


# =========================================================
# ✅ Ensure Folders Exist
# =========================================================
os.makedirs("uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)


# =========================================================
# ✅ SQLite Setup
# =========================================================
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


# =========================================================
# ✅ FastAPI App Setup
# =========================================================
app = FastAPI(title="Motor Data OCR API", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend if exists
app.mount("/static", StaticFiles(directory="static"), name="static")


# =========================================================
# ✅ Root Endpoint
# =========================================================
@app.get("/")
async def root():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "Backend running successfully ✅"}, status_code=200)


# =========================================================
# ✅ OCR Extraction Endpoint
# =========================================================
@app.post("/extract")
async def extract_data(file: UploadFile = File(...), motorName: str = Form(...)):
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))

        # ---- OCR Engine Selection ----
        if TESSERACT_AVAILABLE:
            text = pytesseract.image_to_string(image)
        else:
            import easyocr
            reader = easyocr.Reader(["en"])
            results = reader.readtext(contents, detail=0)
            text = "\n".join(results)

        # ---- Extract Numbers using Regex ----
        def find_value(pattern):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    return None
            return None

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

        # Save temporary image
        temp_path = os.path.join("uploads", f"temp_{file.filename}")
        with open(temp_path, "wb") as f:
            f.write(contents)

        print(f"✅ OCR Extracted for {motorName}")
        return {
            "MotorName": motorName,
            "Power": power,
            "Duty": duty,
            "ERPM": erpm,
            "IBatt": i_batt,
            "IMotor": i_motor,
            "TFET": t_fet,
            "TMotor": t_motor,
            "VoltsIn": volts_in,
            "NormalERPM": normal_erpm,
            "RPM48V": rpm_48v,
            "TempImage": temp_path
        }

    except Exception as e:
        print("❌ OCR Extraction Error:", traceback.format_exc())
        return JSONResponse({"error": f"OCR failed: {str(e)}"}, status_code=500)


# =========================================================
# ✅ Save Data to Database
# =========================================================
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
    TempImage: str = Form(...),
):
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        final_filename = f"{MotorName}_{timestamp}.png"
        final_image_path = os.path.join("uploads", final_filename)

        if os.path.exists(TempImage):
            os.rename(TempImage, final_image_path)
        else:
            return JSONResponse({"error": "Temporary image not found"}, status_code=404)

        image_url = f"/{final_image_path}"

        cursor.execute("""
            INSERT INTO motor_data (
                motor_name, date_time, power, duty, erpm, i_batt, i_motor, 
                t_fet, t_motor, volts_in, normal_erpm, rpm_48v, image_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            MotorName,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            Power, Duty, ERPM, IBatt, IMotor,
            TFET, TMotor, VoltsIn, NormalERPM, RPM48V, image_url
        ))
        conn.commit()

        print(f"✅ Data saved for motor: {MotorName}")
        return {"status": "success", "message": "Data saved successfully"}

    except Exception as e:
        print("❌ Save Error:", traceback.format_exc())
        return JSONResponse({"error": f"Database save failed: {str(e)}"}, status_code=500)


# =========================================================
# ✅ Export Excel Endpoint
# =========================================================
@app.get("/export")
async def export_excel():
    try:
        df = pd.read_sql_query("SELECT * FROM motor_data", conn)
        excel_file = "data.xlsx"
        df.to_excel(excel_file, index=False)

        print("✅ Data exported successfully")
        return FileResponse(
            excel_file,
            filename="motor_data.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        print("❌ Export Error:", traceback.format_exc())
        return JSONResponse({"error": f"Excel export failed: {str(e)}"}, status_code=500)
