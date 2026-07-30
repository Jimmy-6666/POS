(() => {
  const button = document.querySelector('#cameraScanButton');
  const photo = document.querySelector('#barcodePhoto');
  const video = document.querySelector('#barcodeVideo');
  const message = document.querySelector('#cameraMessage');
  const barcodeInput = document.querySelector('#countBarcode');
  const quantityInput = document.querySelector('#countQuantity');
  const productSelect = document.querySelector('select[name="product_uuid"]');
  const scannedProduct = document.querySelector('#scannedProduct');
  if (!barcodeInput || !quantityInput) return;
  let lookupSequence = 0;

  const found = code => {
    const lookupId = ++lookupSequence;
    barcodeInput.value = code;
    if (productSelect) productSelect.value = '';
    if (message) {
      message.classList.remove('scan-error', 'scan-success');
      message.textContent = `อ่านบาร์โค้ด ${code} แล้ว — กำลังค้นหาสินค้า`;
    }
    quantityInput.closest('label')?.classList.remove('scan-ready');
    if (scannedProduct) {
      scannedProduct.textContent = 'กำลังค้นหาชื่อสินค้า...';
      scannedProduct.classList.remove('not-found');
    }
    fetch(`/stock-counts/product-lookup?barcode=${encodeURIComponent(code)}`)
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error);
        if (lookupId !== lookupSequence) return;
        if (scannedProduct) {
          scannedProduct.textContent = `สินค้า: ${data.name}`;
          scannedProduct.classList.remove('not-found');
        }
        if (message) {
          message.classList.remove('scan-error');
          message.classList.add('scan-success');
          message.textContent = `พบสินค้า ${data.name} — กรอกจำนวนแล้วกดยืนยันได้เลย`;
        }
        quantityInput.closest('label')?.classList.add('scan-ready');
        quantityInput.focus({preventScroll: true});
        quantityInput.select();
        quantityInput.scrollIntoView({behavior: 'smooth', block: 'center'});
      })
      .catch(error => {
        if (lookupId !== lookupSequence) return;
        if (scannedProduct) {
          scannedProduct.textContent = error.message || 'ไม่พบสินค้าจากบาร์โค้ดนี้';
          scannedProduct.classList.add('not-found');
        }
        if (message) {
          message.classList.remove('scan-success');
          message.classList.add('scan-error');
          message.textContent = 'ไม่พบสินค้า — พร้อมสแกนสินค้าชิ้นถัดไป';
        }
        quantityInput.value = '';
        barcodeInput.value = '';
        barcodeInput.focus({preventScroll: true});
        barcodeInput.select();
      });
  };

  barcodeInput.addEventListener('change', () => {
    const code = barcodeInput.value.trim();
    if (code) found(code);
  });

  productSelect?.addEventListener('change', () => {
    lookupSequence += 1;
    const option = productSelect.selectedOptions[0];
    if (scannedProduct) {
      scannedProduct.textContent = option?.value
        ? `สินค้า: ${option.textContent.split(' · ')[0]}`
        : 'ยังไม่ได้เลือกสินค้า';
    }
  });

  if (button && photo && video && message) {
    if (window.PosBarcodeCamera) {
      window.PosBarcodeCamera.attach({
        button,
        photoInput: photo,
        video,
        message,
        onFound: found,
      });
    } else {
      button.disabled = true;
      message.classList.add('scan-error');
      message.textContent = 'โหลดตัวสแกนกล้องไม่สำเร็จ กรุณารีเฟรชหน้าแล้วลองใหม่';
    }
  }
})();
