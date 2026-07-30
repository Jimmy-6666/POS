(() => {
  const DEFAULT_FORMATS = ['ean_13', 'ean_8', 'code_128', 'upc_a', 'upc_e'];

  const withTimeout = (promise, milliseconds = 12000) => Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(
      new Error('ใช้เวลาอ่านรูปนานเกินไป กรุณาถ่ายใหม่ให้บาร์โค้ดใหญ่และชัดขึ้น')
    ), milliseconds))
  ]);

  const nativeDetector = () => {
    if (!('BarcodeDetector' in window)) return null;
    try {
      return new BarcodeDetector({formats: DEFAULT_FORMATS});
    } catch (_error) {
      return null;
    }
  };

  const fallbackReader = () => window.ZXingBrowser?.BrowserMultiFormatReader
    ? new window.ZXingBrowser.BrowserMultiFormatReader()
    : null;

  const attach = ({
    button,
    photoInput,
    video,
    message,
    onFound,
    fallbackToPhoto = false,
  }) => {
    if (!button || !video || !message || typeof onFound !== 'function') return null;

    const openLabel = button.textContent;
    let liveStream = null;
    let fallbackControls = null;
    let scanFrame = null;
    let active = false;
    let delivered = false;

    const setMessage = (text, state = '') => {
      message.classList.remove('scan-error', 'scan-success');
      if (state) message.classList.add(state);
      message.textContent = text;
    };

    const stop = () => {
      active = false;
      if (scanFrame !== null) cancelAnimationFrame(scanFrame);
      scanFrame = null;
      try {
        fallbackControls?.stop();
      } catch (_error) {}
      fallbackControls = null;
      liveStream?.getTracks().forEach(track => track.stop());
      liveStream = null;
      if (video.srcObject) video.srcObject = null;
      video.hidden = true;
      button.disabled = false;
      button.textContent = openLabel;
      button.setAttribute('aria-pressed', 'false');
    };

    const showError = error => {
      stop();
      setMessage(
        error?.message || 'อ่านบาร์โค้ดไม่สำเร็จ กรุณาลองใหม่',
        'scan-error'
      );
    };

    const found = value => {
      const code = String(value || '').trim();
      if (!code || delivered) return;
      delivered = true;
      stop();
      setMessage(`อ่านบาร์โค้ด ${code} สำเร็จ`, 'scan-success');
      onFound(code);
    };

    const openPhotoFallback = () => {
      if (!photoInput) return false;
      stop();
      setMessage('กำลังเปิดกล้องถ่ายบาร์โค้ด กรุณาถ่ายให้ตรงและชัด');
      photoInput.click();
      return true;
    };

    button.addEventListener('click', async () => {
      if (active) {
        stop();
        setMessage('ปิดกล้องแล้ว สามารถสแกนหรือกรอกบาร์โค้ดต่อได้');
        return;
      }

      delivered = false;
      setMessage('กำลังขอสิทธิ์เปิดกล้อง...');
      if ((!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) && fallbackToPhoto) {
        openPhotoFallback();
        return;
      }

      try {
        if (!window.isSecureContext) {
          throw new Error('กล้องสดต้องเปิดผ่าน HTTPS หรือ localhost ใช้ปุ่มถ่ายรูปแทนบนมือถือได้');
        }
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error('อุปกรณ์นี้ไม่รองรับกล้องผ่านเบราว์เซอร์');
        }

        const detector = nativeDetector();
        const reader = detector ? null : fallbackReader();
        if (!detector && !reader) {
          throw new Error('โหลดตัวอ่านบาร์โค้ดไม่สำเร็จ กรุณารีเฟรชหน้าแล้วลองใหม่');
        }

        active = true;
        button.textContent = 'ปิดกล้อง';
        button.setAttribute('aria-pressed', 'true');
        video.hidden = false;
        setMessage('เล็งกล้องไปที่บาร์โค้ด');

        if (reader) {
          fallbackControls = await reader.decodeFromVideoDevice(
            undefined,
            video,
            result => {
              if (result) found(result.getText());
            }
          );
          return;
        }

        liveStream = await navigator.mediaDevices.getUserMedia({
          video: {facingMode: {ideal: 'environment'}}
        });
        if (!active) {
          liveStream.getTracks().forEach(track => track.stop());
          liveStream = null;
          return;
        }
        video.srcObject = liveStream;
        await video.play();

        const scan = async () => {
          if (!active) return;
          try {
            const codes = await detector.detect(video);
            if (codes.length) {
              found(codes[0].rawValue);
              return;
            }
          } catch (_error) {}
          scanFrame = requestAnimationFrame(scan);
        };
        scanFrame = requestAnimationFrame(scan);
      } catch (error) {
        if (fallbackToPhoto && openPhotoFallback()) return;
        showError(error);
      }
    });

    photoInput?.addEventListener('change', async () => {
      const file = photoInput.files?.[0];
      if (!file) return;
      delivered = false;
      setMessage('กำลังอ่านรูปบาร์โค้ด...');
      let bitmap;
      try {
        const detector = nativeDetector();
        if (detector) {
          bitmap = await withTimeout(createImageBitmap(file));
          const codes = await withTimeout(detector.detect(bitmap));
          if (!codes.length) {
            throw new Error('ไม่พบบาร์โค้ดในรูป กรุณาถ่ายให้ตรง ชัด และให้บาร์โค้ดกินพื้นที่ส่วนใหญ่ของภาพ');
          }
          found(codes[0].rawValue);
        } else {
          const reader = fallbackReader();
          if (!reader) {
            throw new Error('โหลดตัวอ่านบาร์โค้ดไม่สำเร็จ กรุณารีเฟรชหน้าแล้วลองใหม่');
          }
          const imageUrl = URL.createObjectURL(file);
          try {
            const result = await withTimeout(reader.decodeFromImageUrl(imageUrl));
            found(result.getText());
          } finally {
            URL.revokeObjectURL(imageUrl);
          }
        }
      } catch (error) {
        showError(error);
      } finally {
        bitmap?.close?.();
        photoInput.value = '';
      }
    });

    window.addEventListener('pagehide', stop);
    return {stop};
  };

  window.PosBarcodeCamera = {attach};
})();
