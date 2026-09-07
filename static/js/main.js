document.addEventListener('DOMContentLoaded', () => {
  // 1. Allergy Profile card selection
  const allergyCards = document.querySelectorAll('.allergy-card-select');
  allergyCards.forEach(card => {
    const cb = card.querySelector('input[type="checkbox"]');
    if (cb) {
      if (cb.checked) card.classList.add('selected');
      card.addEventListener('click', (e) => {
        if (e.target !== cb) {
          cb.checked = !cb.checked;
        }
        card.classList.toggle('selected', cb.checked);
      });
    }
  });

  // 2. Dropzone file upload handler
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('label_image');
  const filePreview = document.getElementById('file-preview');
  const previewImg = document.getElementById('preview-img');
  const sampleInput = document.getElementById('sample_choice');
  const scanForm = document.getElementById('scan-form');
  const procIndicator = document.getElementById('processing-indicator');

  if (dropzone && fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());

    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        handleFileChange();
      }
    });

    fileInput.addEventListener('change', handleFileChange);
  }

  function handleFileChange() {
    if (fileInput.files && fileInput.files[0]) {
      const reader = new FileReader();
      reader.onload = (e) => {
        if (previewImg) previewImg.src = e.target.result;
        if (filePreview) filePreview.style.display = 'block';
        if (sampleInput) sampleInput.value = '';
      };
      reader.readAsDataURL(fileInput.files[0]);
    }
  }

  // Show processing indicator on form submission
  if (scanForm && procIndicator) {
    scanForm.addEventListener('submit', () => {
      procIndicator.style.display = 'block';
      const btn = document.getElementById('submit-scan-btn');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i data-lucide="loader-2" class="spin"></i> Processing...';
        if (window.lucide) lucide.createIcons();
      }
    });
  }

  // 3. Camera Capture Handler
  const startCameraBtn = document.getElementById('start-camera-btn');
  const videoElement = document.getElementById('camera-video');
  const captureBtn = document.getElementById('capture-btn');

  if (startCameraBtn && videoElement && captureBtn) {
    startCameraBtn.addEventListener('click', async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
        videoElement.srcObject = stream;
        videoElement.style.display = 'block';
        captureBtn.style.display = 'inline-flex';
        startCameraBtn.style.display = 'none';
      } catch (err) {
        alert('Camera access error: ' + err.message);
      }
    });

    captureBtn.addEventListener('click', () => {
      const canvas = document.createElement('canvas');
      canvas.width = videoElement.videoWidth || 640;
      canvas.height = videoElement.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
      
      canvas.toBlob((blob) => {
        const file = new File([blob], "camera_capture.jpg", { type: "image/jpeg" });
        const dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
        handleFileChange();

        // Stop camera stream
        const stream = videoElement.srcObject;
        if (stream) {
          stream.getTracks().forEach(track => track.stop());
        }
        videoElement.style.display = 'none';
        captureBtn.style.display = 'none';
        startCameraBtn.style.display = 'inline-flex';
      }, 'image/jpeg');
    });
  }

  // 4. Sample Selection Handler
  window.selectSample = function(sampleName) {
    if (sampleInput) {
      sampleInput.value = sampleName;
      if (fileInput) fileInput.value = '';
      if (previewImg) previewImg.src = `/static/sample_labels/${sampleName}`;
      if (filePreview) filePreview.style.display = 'block';
    }
  };
});
