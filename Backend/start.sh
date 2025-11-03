#!/bin/bash
apt-get update -y
apt-get install -y tesseract-ocr
uvicorn main:app --host 0.0.0.0 --port $PORT
