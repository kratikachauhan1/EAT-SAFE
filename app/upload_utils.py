import os
import uuid
import logging
from PIL import Image
from werkzeug.utils import secure_filename

logger = logging.getLogger('eatsafe')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff'}

def is_allowed_extension(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_and_save_upload(file_obj, upload_folder):
    """
    Validates uploaded file format, verifies actual image header integrity using Pillow,
    prevents path traversal, generates a safe unique filename, and saves the file.
    
    Returns:
        tuple: (saved_filename, error_message)
    """
    if not file_obj or not file_obj.filename or file_obj.filename.strip() == '':
        return None, "No file selected for upload."

    original_filename = secure_filename(file_obj.filename)
    if not is_allowed_extension(original_filename):
        return None, "Unsupported file format. Please upload PNG, JPG, JPEG, WEBP, BMP, or TIFF."

    # Validate image header integrity with Pillow
    try:
        file_obj.stream.seek(0)
        img = Image.open(file_obj.stream)
        img.verify()
        file_obj.stream.seek(0)
    except Exception as e:
        logger.warning(f"Image validation failed for file {file_obj.filename}: {e}")
        return None, "The uploaded file is corrupted or not a valid image format."

    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
    safe_filename = f"scan_{uuid.uuid4().hex}.{ext}"

    os.makedirs(upload_folder, exist_ok=True)
    target_path = os.path.abspath(os.path.join(upload_folder, safe_filename))

    # Path traversal safeguard
    canonical_folder = os.path.abspath(upload_folder)
    if not target_path.startswith(canonical_folder):
        logger.error(f"Path traversal attempt detected: {target_path}")
        return None, "Security violation: Invalid upload target path."

    file_obj.save(target_path)
    return safe_filename, None
