(() => {
  const scanForm = document.querySelector('[data-quick-scan-form]');
  const scanInput = document.querySelector('#quickProductBarcode');
  const cameraButton = document.querySelector('#quickCameraScanButton');
  const cameraPhoto = document.querySelector('#quickBarcodePhoto');
  const cameraVideo = document.querySelector('#quickBarcodeVideo');
  const cameraMessage = document.querySelector('#quickCameraMessage');
  const editForm = document.querySelector('[data-quick-product-form]');
  const saveButton = document.querySelector('#quickProductSave');
  const alreadyImagedDialog = document.querySelector('#quickProductAlreadyImaged');
  const editorDialog = document.querySelector('[data-quick-product-dialog]');
  const editorDetails = document.querySelector('[data-quick-editor-details]');
  const priceInput = document.querySelector('#quickProductPrice');
  const pricePanel = document.querySelector('[data-quick-price-entry]');
  const priceOutput = document.querySelector('#quickPriceOutput');
  const priceConfirm = document.querySelector('[data-price-confirm]');
  const openPriceButton = document.querySelector('[data-open-price-numpad]');
  const productNameInput = document.querySelector('textarea[name="name_th"]');
  const currentProductNames = document.querySelectorAll('[data-quick-product-current-name]');
  const imageBrowse = document.querySelector('#productImageBrowse');
  const imageCamera = document.querySelector('#productImageCamera');
  const imagePreview = document.querySelector('#productImagePreview');
  const imagePreviewElement = imagePreview?.querySelector('img');
  const imageRemove = document.querySelector('#removeProductImage');
  const currentImage = document.querySelector('#currentProductImage');
  const mobileEditorViewport = window.matchMedia('(max-width: 600px)');
  let scanSubmitted = false;
  let priceAccepted = false;
  let replaceNextDigit = true;
  let imagePreviewGeneration = 0;

  const setImagePreviewVisible = visible => {
    if (!imagePreview) return;
    imagePreview.hidden = !visible;
    imagePreview.classList.toggle('is-visible', visible);
    if (currentImage) currentImage.hidden = visible;
  };

  const clearImagePreview = () => {
    imagePreviewGeneration += 1;
    imagePreviewElement?.removeAttribute('src');
    setImagePreviewVisible(false);
  };

  const showImagePreview = (input, otherInput) => {
    const file = input?.files?.[0];
    if (!file || !imagePreviewElement) return;
    if (otherInput) otherInput.value = '';
    const previewGeneration = ++imagePreviewGeneration;
    const reader = new FileReader();
    reader.addEventListener('load', () => {
      if (previewGeneration !== imagePreviewGeneration) return;
      if (typeof reader.result !== 'string' || !reader.result.startsWith('data:image/')) {
        clearImagePreview();
        return;
      }
      imagePreviewElement.src = reader.result;
      imagePreviewElement.alt = 'ตัวอย่างรูปสินค้าที่เลือก';
      setImagePreviewVisible(true);
    }, {once: true});
    reader.addEventListener('error', () => {
      if (previewGeneration === imagePreviewGeneration) clearImagePreview();
    }, {once: true});
    reader.readAsDataURL(file);
  };

  imageBrowse?.addEventListener('change', () => {
    showImagePreview(imageBrowse, imageCamera);
  });
  imageCamera?.addEventListener('change', () => {
    showImagePreview(imageCamera, imageBrowse);
  });
  imageRemove?.addEventListener('click', () => {
    if (imageBrowse) imageBrowse.value = '';
    if (imageCamera) imageCamera.value = '';
    clearImagePreview();
    imageBrowse?.focus({preventScroll: true});
  });

  const editorIsModal = () => {
    try {
      return editorDialog?.matches(':modal') || false;
    } catch (_error) {
      return false;
    }
  };

  const updatePrice = value => {
    if (!priceInput) return;
    priceInput.value = value;
    priceOutput && (priceOutput.textContent = `${value || '0'} บาท`);
    priceInput.dispatchEvent(new Event('input', {bubbles: true}));
  };

  const setPriceEntryOpen = open => {
    if (!pricePanel || !editorDetails) return;
    pricePanel.hidden = !open;
    editorDetails.inert = open;
    editorDialog?.classList.toggle('quick-price-entry-open', open);
    if (open) {
      replaceNextDigit = true;
      requestAnimationFrame(() => {
        pricePanel.querySelector('[data-price-key]')?.focus({preventScroll: true});
      });
    }
  };

  const syncEditorDialog = () => {
    if (!editorDialog) return;

    if (mobileEditorViewport.matches) {
      document.body.classList.add('quick-product-modal-open');
      if (typeof editorDialog.showModal === 'function' && !editorIsModal()) {
        editorDialog.removeAttribute('open');
        editorDialog.showModal();
      } else if (!editorDialog.open) {
        editorDialog.setAttribute('open', '');
      }
      if (priceInput) priceInput.readOnly = true;
      if (!priceAccepted) setPriceEntryOpen(true);
      return;
    }

    document.body.classList.remove('quick-product-modal-open');
    if (editorIsModal()) editorDialog.close();
    editorDialog.setAttribute('open', '');
    if (priceInput) priceInput.readOnly = false;
    setPriceEntryOpen(false);
  };

  if (scanForm && scanInput) {
    scanForm.addEventListener('submit', event => {
      scanInput.value = scanInput.value.trim();
      if (!scanInput.value || scanSubmitted) {
        event.preventDefault();
        if (!scanSubmitted) scanInput.focus();
        return;
      }
      scanSubmitted = true;
    });

    if (cameraButton && cameraPhoto && cameraVideo && cameraMessage) {
      if (window.PosBarcodeCamera) {
        window.PosBarcodeCamera.attach({
          button: cameraButton,
          photoInput: cameraPhoto,
          video: cameraVideo,
          message: cameraMessage,
          fallbackToPhoto: true,
          onFound: code => {
            if (scanSubmitted) return;
            scanInput.value = code;
            cameraMessage.textContent = `อ่านบาร์โค้ด ${code} สำเร็จ — กำลังค้นหาสินค้า`;
            scanForm.requestSubmit();
          },
        });
      } else {
        cameraButton.disabled = true;
        cameraMessage.classList.add('scan-error');
        cameraMessage.textContent = 'โหลดตัวสแกนกล้องไม่สำเร็จ กรุณารีเฟรชหน้าแล้วลองใหม่';
      }
    }
  }

  if (pricePanel && priceInput) {
    pricePanel.addEventListener('click', event => {
      const button = event.target.closest('button');
      if (!button) return;

      if (button.dataset.priceKey !== undefined) {
        const current = priceInput.value.replace(/\D/g, '');
        const next = replaceNextDigit
          ? button.dataset.priceKey
          : `${current}${button.dataset.priceKey}`;
        updatePrice(next.replace(/^0+(?=\d)/, ''));
        replaceNextDigit = false;
      }
      if (button.dataset.priceAction === 'backspace') {
        updatePrice(priceInput.value.replace(/\D/g, '').slice(0, -1));
        replaceNextDigit = false;
      }
      if (button.dataset.priceAction === 'clear') {
        updatePrice('');
        replaceNextDigit = false;
      }
    });
  }

  priceConfirm?.addEventListener('click', () => {
    if (!priceInput.value) updatePrice('0');
    priceAccepted = true;
    setPriceEntryOpen(false);
    document.querySelector('#productImageCamera')?.focus({preventScroll: true});
  });

  const reopenPriceEntry = () => {
    if (!mobileEditorViewport.matches) return;
    priceAccepted = false;
    setPriceEntryOpen(true);
  };
  openPriceButton?.addEventListener('click', reopenPriceEntry);
  priceInput?.addEventListener('click', reopenPriceEntry);

  productNameInput?.addEventListener('input', () => {
    currentProductNames.forEach(element => {
      element.textContent = productNameInput.value.trim() || 'ยังไม่ได้ระบุชื่อสินค้า';
    });
  });

  if (editForm && saveButton) {
    editForm.addEventListener('submit', () => {
      saveButton.disabled = true;
      saveButton.textContent = 'กำลังบันทึก...';
    });
  }

  if (alreadyImagedDialog && typeof alreadyImagedDialog.showModal === 'function') {
    alreadyImagedDialog.removeAttribute('open');
    alreadyImagedDialog.showModal();
  }

  if (editorDialog) {
    syncEditorDialog();
    editorDialog.addEventListener('close', () => {
      document.body.classList.remove('quick-product-modal-open');
      scanInput?.focus();
    });
    if (typeof mobileEditorViewport.addEventListener === 'function') {
      mobileEditorViewport.addEventListener('change', syncEditorDialog);
    } else {
      mobileEditorViewport.addListener(syncEditorDialog);
    }
  }
})();
