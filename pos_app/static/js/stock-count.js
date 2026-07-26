(() => {
  const button = document.querySelector('#cameraScanButton');
  const photo = document.querySelector('#barcodePhoto');
  const video = document.querySelector('#barcodeVideo');
  const message = document.querySelector('#cameraMessage');
  const barcodeInput = document.querySelector('#countBarcode');
  const quantityInput = document.querySelector('#countQuantity');
  const productSelect = document.querySelector('select[name="product_id"]');
  const scannedProduct = document.querySelector('#scannedProduct');
  if (!button || !photo || !quantityInput) return;

  const nativeDetector = () => 'BarcodeDetector' in window
    ? new BarcodeDetector({formats: ['ean_13', 'ean_8', 'code_128', 'upc_a', 'upc_e']})
    : null;
  const fallbackReader = () => window.ZXingBrowser?.BrowserMultiFormatReader
    ? new window.ZXingBrowser.BrowserMultiFormatReader()
    : null;
  const withTimeout = (promise, milliseconds = 12000) => Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error('ใช้เวลาอ่านรูปนานเกินไป กรุณาถ่ายใหม่ให้บาร์โค้ดใหญ่และชัดขึ้น')), milliseconds))
  ]);
  const showError = error => {
    message.classList.remove('scan-success');
    message.classList.add('scan-error');
    message.textContent = error?.message || 'อ่านบาร์โค้ดไม่สำเร็จ กรุณาลองใหม่';
  };
  const found = code => {
    barcodeInput.value = code;
    if (productSelect) productSelect.value = '';
    message.classList.remove('scan-error');
    message.classList.add('scan-success');
    message.textContent = `อ่านบาร์โค้ด ${code} สำเร็จ — กรอกจำนวนแล้วกดยืนยันได้เลย`;
    if (scannedProduct) {
      scannedProduct.textContent = 'กำลังค้นหาชื่อสินค้า...';
      scannedProduct.classList.remove('not-found');
      fetch(`/stock-counts/product-lookup?barcode=${encodeURIComponent(code)}`)
        .then(async response => {
          const data = await response.json();
          if (!response.ok) throw new Error(data.error);
          scannedProduct.textContent = `สินค้า: ${data.name}`;
        })
        .catch(error => {
          scannedProduct.textContent = error.message || 'ไม่พบสินค้าจากบาร์โค้ดนี้';
          scannedProduct.classList.add('not-found');
        });
    }
    quantityInput.closest('label')?.classList.add('scan-ready');
    quantityInput.focus({preventScroll: true});
    quantityInput.select();
    quantityInput.scrollIntoView({behavior: 'smooth', block: 'center'});
  };

  barcodeInput.addEventListener('change', () => {
    if (barcodeInput.value.trim()) found(barcodeInput.value.trim());
  });
  productSelect?.addEventListener('change', () => {
    const option = productSelect.selectedOptions[0];
    if (scannedProduct) scannedProduct.textContent = option?.value ? `สินค้า: ${option.textContent.split(' · ')[0]}` : 'ยังไม่ได้เลือกสินค้า';
  });

  button.onclick = async () => {
    message.textContent = 'กำลังขอสิทธิ์เปิดกล้อง...';
    try {
      if (!window.isSecureContext) throw new Error('กล้องสดต้องเปิดผ่าน HTTPS หรือ localhost ใช้ปุ่มถ่ายรูปแทนบนมือถือได้');
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('อุปกรณ์นี้ไม่รองรับกล้องผ่านเบราว์เซอร์');
      const scanDetector = nativeDetector();
      if (!scanDetector) {
        const reader = fallbackReader();
        if (!reader) throw new Error('โหลดตัวอ่านบาร์โค้ดไม่สำเร็จ กรุณารีเฟรชหน้าแล้วลองใหม่');
        video.hidden = false;
        message.textContent = 'เล็งกล้องไปที่บาร์โค้ด';
        await reader.decodeFromVideoDevice(undefined, video, (result, _error, controls) => {
          if (!result) return;
          found(result.getText());
          controls.stop();
          video.hidden = true;
        });
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: {ideal: 'environment'}}});
      video.srcObject = stream;
      video.hidden = false;
      await video.play();
      message.textContent = 'เล็งกล้องไปที่บาร์โค้ด';
      const scan = async () => {
        if (video.hidden) return;
        try {
          const codes = await scanDetector.detect(video);
          if (codes.length) {
            found(codes[0].rawValue);
            stream.getTracks().forEach(track => track.stop());
            video.hidden = true;
            return;
          }
        } catch (_) {}
        requestAnimationFrame(scan);
      };
      scan();
    } catch (error) { showError(error); }
  };

  photo.onchange = async () => {
    const file = photo.files?.[0];
    if (!file) return;
    message.classList.remove('scan-error', 'scan-success');
    message.textContent = 'กำลังอ่านรูปบาร์โค้ด...';
    let bitmap;
    try {
      const scanDetector = nativeDetector();
      if (scanDetector) {
        bitmap = await withTimeout(createImageBitmap(file));
        const codes = await withTimeout(scanDetector.detect(bitmap));
        if (!codes.length) throw new Error('ไม่พบบาร์โค้ดในรูป กรุณาถ่ายให้ตรง ชัด และให้บาร์โค้ดกินพื้นที่ส่วนใหญ่ของภาพ');
        found(codes[0].rawValue);
      } else {
        const reader = fallbackReader();
        if (!reader) throw new Error('โหลดตัวอ่านบาร์โค้ดไม่สำเร็จ กรุณารีเฟรชหน้าแล้วลองใหม่');
        const imageUrl = URL.createObjectURL(file);
        try {
          const result = await withTimeout(reader.decodeFromImageUrl(imageUrl));
          found(result.getText());
        } finally { URL.revokeObjectURL(imageUrl); }
      }
    } catch (error) { showError(error); }
    finally {
      bitmap?.close?.();
      photo.value = '';
    }
  };
})();
