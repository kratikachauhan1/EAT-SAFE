import cv2
import numpy as np

def preprocess_image(image_input):
    """
    Accepts an image path (str) or a numpy uint8 BGR image array.
    Returns:
        processed_image: preprocessed numpy image ready for Tesseract OCR
        metadata: dict containing preprocessing stats/steps applied
    """
    if isinstance(image_input, str):
        img = cv2.imread(image_input)
        if img is None:
            raise ValueError(f"Could not read image from path: {image_input}")
    else:
        img = image_input

    # 1. Resize if image is very small or very large (normalize dimensions for OCR)
    h, w = img.shape[:2]
    target_width = 1200
    if w < 600 or w > 2400:
        scale = target_width / float(w)
        img = cv2.resize(img, (target_width, int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # 2. Grayscale conversion
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # 3. Noise reduction (Fast Non-Local Means Denoising)
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    # 4. Contrast Enhancement using CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    # 5. Image Sharpening kernel
    kernel = np.array([[0, -1, 0],
                       [-1, 5, -1],
                       [0, -1, 0]], dtype=np.float32)
    sharpened = cv2.filter2D(enhanced, -1, kernel)

    # 6. Adaptive Thresholding for crisp binary text
    binary = cv2.adaptiveThreshold(
        sharpened, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 15, 8
    )

    metadata = {
        'original_dimensions': (w, h),
        'processed_dimensions': (sharpened.shape[1], sharpened.shape[0]),
        'steps_applied': ['resize', 'grayscale', 'denoise', 'clahe', 'sharpen', 'adaptive_threshold']
    }

    # Return both grayscale enhanced (better for some Tesseract modes) and binary
    return sharpened, metadata
