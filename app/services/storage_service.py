import os
import uuid
import logging
from PIL import Image

logger = logging.getLogger('eatsafe')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff'}
MAX_IMAGE_DIMENSION = 10000 # Max 10,000 x 10,000 pixels to prevent decompression bombs
MAX_FILE_SIZE_BYTES = 16 * 1024 * 1024 # 16 MB


class StorageService:
    """Storage Service abstraction for local filesystem and S3-compatible cloud storage."""
    
    def __init__(self, upload_folder=None, storage_type=None):
        self.storage_type = (storage_type or os.environ.get('STORAGE_TYPE', 'local')).lower()
        self.upload_folder = upload_folder or os.environ.get(
            'UPLOAD_FOLDER',
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'static', 'uploads')
        )
        os.makedirs(self.upload_folder, exist_ok=True)

    def validate_image(self, file_obj):
        """
        Validate file format, Pillow header integrity, pixel dimensions, and size limit.
        Returns: (is_valid, ext_or_error_msg)
        """
        if not file_obj or not file_obj.filename or file_obj.filename.strip() == '':
            return False, "No file selected for upload."

        filename = file_obj.filename.strip()
        if '.' not in filename:
            return False, "File name missing extension."

        ext = filename.rsplit('.', 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return False, f"Unsupported file format '.{ext}'. Allowed formats: PNG, JPG, JPEG, WEBP, BMP, TIFF."

        # Size check
        file_obj.stream.seek(0, os.SEEK_END)
        size = file_obj.stream.tell()
        file_obj.stream.seek(0)
        
        if size > MAX_FILE_SIZE_BYTES:
            return False, f"File size ({round(size / (1024*1024), 1)} MB) exceeds maximum allowed limit (16 MB)."

        # PIL image byte & pixel dimension validation
        try:
            img = Image.open(file_obj.stream)
            img.verify()
            
            # Re-open after verify() to inspect size dimensions
            file_obj.stream.seek(0)
            img_real = Image.open(file_obj.stream)
            width, height = img_real.size
            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                return False, f"Image dimensions ({width}x{height}) exceed maximum allowed limit ({MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION})."
                
            file_obj.stream.seek(0)
        except Exception as e:
            logger.warning(f"Image security validation failed: {e}")
            return False, "The uploaded file is corrupted or not a valid image format."

        return True, ext

    def save_file(self, file_obj):
        """
        Validates, generates UUID filename, saves image to configured storage.
        Returns: (saved_rel_path, error_msg)
        """
        is_valid, result = self.validate_image(file_obj)
        if not is_valid:
            return None, result

        ext = result
        safe_filename = f"scan_{uuid.uuid4().hex}.{ext}"

        if self.storage_type == 's3':
            # Support AWS S3 / Cloudflare R2 if configured
            try:
                import boto3
                bucket = os.environ.get('STORAGE_BUCKET')
                s3 = boto3.client(
                    's3',
                    endpoint_url=os.environ.get('STORAGE_ENDPOINT'),
                    aws_access_key_id=os.environ.get('STORAGE_ACCESS_KEY'),
                    aws_secret_access_key=os.environ.get('STORAGE_SECRET_KEY')
                )
                file_obj.stream.seek(0)
                s3.upload_fileobj(file_obj.stream, bucket, safe_filename)
                logger.info(f"Uploaded scan file to S3 bucket '{bucket}': {safe_filename}")
                return f"s3://{bucket}/{safe_filename}", None
            except Exception as e:
                logger.error(f"S3 Storage upload failed: {e}. Falling back to local filesystem.")

        # Local Filesystem Storage
        target_path = os.path.abspath(os.path.join(self.upload_folder, safe_filename))
        canonical_folder = os.path.abspath(self.upload_folder)

        # Path traversal safeguard
        if not target_path.startswith(canonical_folder):
            logger.error(f"Path traversal attempt detected: {target_path}")
            return None, "Security violation: Invalid upload target path."

        file_obj.stream.seek(0)
        file_obj.save(target_path)
        rel_path = f"uploads/{safe_filename}"
        return rel_path, None

    def delete_file(self, rel_path):
        """Delete file from disk if path exists."""
        if not rel_path or not rel_path.startswith('uploads/'):
            return
        filename = os.path.basename(rel_path)
        abs_path = os.path.abspath(os.path.join(self.upload_folder, filename))
        if os.path.exists(abs_path):
            try:
                os.remove(abs_path)
                logger.info(f"Deleted storage file: {abs_path}")
            except Exception as e:
                logger.error(f"Error removing storage file '{abs_path}': {e}")


# Global Singleton Service
storage_service = StorageService()
