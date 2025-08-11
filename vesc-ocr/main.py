import re
from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import pytesseract
from PIL import Image
import io
import os

# Remove this line for deployment (Windows-only)
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = FastAPI()

# Allow all origins for CORS (you can restrict this later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (your HTML and any other static assets)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html at root
@app.get("/")
async def root():
    return FileResponse(os.path.join("static", "index.html"))

@app.post("/extract")
async def extract_data(file: UploadFile = File(...)):
    image_data = await file.read()
    image = Image.open(io.BytesIO(image_data))
    text = pytesseract.image_to_string(image)
    print("OCR OUTPUT:\n", text)

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

    return {
        "Power": power,
        "Duty": duty,
        "ERPM": erpm,
        "I Batt": i_batt,
        "I Motor": i_motor,
        "T FET": t_fet,
        "T Motor": t_motor,
        "Volts In": volts_in,
        "Normal ERPM": normal_erpm,
        "48V RPM": rpm_48v
    }