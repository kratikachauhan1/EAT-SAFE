import os
import shutil
import pytesseract
from PIL import Image
import numpy as np

def find_tesseract_cmd():
    """Locate Tesseract executable on Windows or Linux."""
    if shutil.which("tesseract"):
        return "tesseract"
        
    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
        r"D:\Program Files\Tesseract-OCR\tesseract.exe"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
            
    return None

# Configure pytesseract command path if found
tesseract_bin = find_tesseract_cmd()
if tesseract_bin:
    pytesseract.pytesseract.tesseract_cmd = tesseract_bin


def extract_text_from_image(image_input):
    """
    Extract text and compute average OCR confidence.
    Accepts image file path, PIL Image, or numpy array.
    Returns:
        raw_text (str): Extracted text
        confidence (float): Average confidence score (0.0 to 100.0)
        is_reliable (bool): True if confidence >= 40.0 and text length >= 10
    """
    cmd = find_tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    if isinstance(image_input, str):
        img = Image.open(image_input)
    elif isinstance(image_input, np.ndarray):
        img = Image.fromarray(image_input)
    else:
        img = image_input

    try:
        # Extract full text
        raw_text = pytesseract.image_to_string(img, lang='eng')
        
        # Calculate confidence from image_to_data
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        confidences = [int(c) for c in data.get('conf', []) if c != '-1' and str(c).isdigit()]
        
        if confidences:
            avg_conf = float(sum(confidences) / len(confidences))
        else:
            avg_conf = 0.0

        cleaned_len = len(raw_text.strip())
        is_reliable = (avg_conf >= 40.0) and (cleaned_len >= 8)

        return raw_text, round(avg_conf, 2), is_reliable

    except Exception as e:
        return f"OCR Error: {str(e)}", 0.0, False
