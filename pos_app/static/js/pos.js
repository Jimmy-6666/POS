(() => {
  const app = document.querySelector('#posApp');
  if (!app) return;
  const $ = (selector) => document.querySelector(selector);
  const csrf = app.dataset.csrf;
  const money = (satang) => `${Math.round(satang / 100).toLocaleString('th-TH')} บาท`;
  const escapeHtml = (text) => { const node = document.createElement('div'); node.textContent = text || ''; return node.innerHTML; };
  const manualPriceDialog = $('#manualPriceDialog');
  const manualBarcode = 'MANUALPRICE';
  let products = [], buttonGroups = [], currentGroup = null, catalogMode = 'groups', catalogPage = 1;
  let cart = [], total = 0, paymentMethod = 'cash', completing = false, manualPriceSaving = false, manualPriceContext = null, searchTimer, scannerTimer, scannerStream = [];
  const catalogPageSize = 9;

  // Keyboard-wedge barcode readers emit physical keyboard codes.  Those codes
  // remain stable even when Windows/iOS has a Thai keyboard layout selected.
  const scannerCharacter = (code) => {
    if (/^Digit\d$/.test(code)) return code.slice(-1);
    if (/^Numpad\d$/.test(code)) return code.slice(-1);
    if (/^Key[A-Z]$/.test(code)) return code.slice(-1);
    return ({ Minus: '-', NumpadSubtract: '-', Slash: '/', NumpadDivide: '/', Period: '.', NumpadDecimal: '.' })[code] || '';
  };
  const scannerBlocked = () => ['#manualPriceDialog', '#paymentDialog', '#saleSuccessDialog', '#heldDialog'].some((selector) => $(selector)?.open);
  const scannerEntryTarget = (target) => target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
  function resetScannerStream() { scannerStream = []; clearTimeout(scannerTimer); }
  function scannerIsFast() {
    return scannerStream.length >= 3 && scannerStream.every((entry, index) => index === 0 || entry.at - scannerStream[index - 1].at <= 75);
  }
  function restoreScannerTarget(stream) {
    if (!stream || !scannerEntryTarget(stream.target)) return;
    stream.target.value = stream.value;
    if (stream.target.setSelectionRange && stream.selectionStart !== null) stream.target.setSelectionRange(stream.selectionStart, stream.selectionEnd);
    stream.target.dispatchEvent(new Event('input', { bubbles: true }));
  }
  function blockScannerInsideManualPrice(event) {
    if (!manualPriceDialog.open) return false;
    if (event.ctrlKey || event.altKey || event.metaKey || event.isComposing) {
      resetScannerStream();
      return true;
    }
    if (event.key === 'Enter') {
      if (scannerIsFast()) {
        const stream = scannerStream[0];
        event.preventDefault();
        event.stopPropagation();
        restoreScannerTarget(stream);
        $('#manualPriceError').textContent = 'กรุณาระบุราคาให้เสร็จก่อนสแกนสินค้าชิ้นถัดไป';
        $('#manualPriceInput').focus({ preventScroll: true });
      }
      resetScannerStream();
      return true;
    }
    const character = scannerCharacter(event.code);
    if (!character || event.key.length !== 1) {
      resetScannerStream();
      return true;
    }
    if (!scannerStream.length) {
      scannerStream.push({ code: event.code, at: performance.now(), target: event.target, value: scannerEntryTarget(event.target) ? event.target.value : '', selectionStart: scannerEntryTarget(event.target) ? event.target.selectionStart : null, selectionEnd: scannerEntryTarget(event.target) ? event.target.selectionEnd : null });
    } else scannerStream.push({ code: event.code, at: performance.now() });
    clearTimeout(scannerTimer);
    scannerTimer = setTimeout(resetScannerStream, 120);
    return true;
  }
  function receiveScannerKey(event) {
    if (blockScannerInsideManualPrice(event)) return;
    if (scannerBlocked() || event.ctrlKey || event.altKey || event.metaKey || event.isComposing) { resetScannerStream(); return; }
    if (event.key === 'Enter') {
      if (!scannerIsFast()) { resetScannerStream(); return; }
      const value = scannerStream.map((entry) => scannerCharacter(entry.code)).join('');
      const stream = scannerStream[0];
      resetScannerStream();
      if (!value) return;
      event.preventDefault();
      event.stopPropagation();
      restoreScannerTarget(stream);
      const lookup = $('#productLookup');
      lookup.value = value;
      lookup.focus({ preventScroll: true });
      clearTimeout(searchTimer);
      addFromLookup({ scanner: true });
      return;
    }
    const character = scannerCharacter(event.code);
    if (!character || event.key.length !== 1) { resetScannerStream(); return; }
    if (!scannerStream.length) {
      scannerStream.push({ code: event.code, at: performance.now(), target: event.target, value: scannerEntryTarget(event.target) ? event.target.value : '', selectionStart: scannerEntryTarget(event.target) ? event.target.selectionStart : null, selectionEnd: scannerEntryTarget(event.target) ? event.target.selectionEnd : null });
    } else scannerStream.push({ code: event.code, at: performance.now() });
    clearTimeout(scannerTimer);
    scannerTimer = setTimeout(resetScannerStream, 120);
  }

  async function api(url, options = {}) {
    options.headers = { ...(options.headers || {}), 'X-CSRF-Token': csrf };
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'เกิดข้อผิดพลาด กรุณาลองใหม่');
    return data;
  }
  function message(text = '', error = false) {
    const box = $('#posMessage');
    box.textContent = text;
    box.className = `pos-message ${text ? (error ? 'error' : 'success') : ''}`;
  }
  function playManualPriceAlert(shortPrompt = false) {
    const audio = shortPrompt ? $('#manualPriceAudio') : $('#missingProductPriceAudio');
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
    audio.play().catch(() => {});
  }
  function positionedCatalogRows() {
    const rows = catalogMode === 'groups' ? buttonGroups : products;
    if (catalogMode !== 'search') return rows;
    return rows.map((row, index) => ({ ...row, position: index + 1 }));
  }
  function catalogPageCount(rows = positionedCatalogRows()) {
    const lastPosition = rows.reduce((highest, row) => Math.max(highest, Number(row.position) || 0), 0);
    return Math.max(1, Math.ceil(lastPosition / catalogPageSize));
  }
  function renderCatalog() {
    const rows = positionedCatalogRows();
    const pageCount = catalogPageCount(rows);
    catalogPage = Math.min(Math.max(1, catalogPage), pageCount);
    const firstPosition = ((catalogPage - 1) * catalogPageSize) + 1;
    const slots = Array.from({ length: catalogPageSize }, (_, index) => {
      const position = firstPosition + index;
      return rows.find((row) => Number(row.position) === position) || null;
    });
    const title = catalogMode === 'groups'
      ? 'เลือกเมนูสินค้า'
      : catalogMode === 'search'
        ? 'ผลการค้นหาสินค้าทั้งหมด'
        : currentGroup?.name_th || 'สินค้าในเมนู';
    $('#catalogTitle').textContent = title;
    $('#catalogBackButton').hidden = catalogMode === 'groups';
    $('#resultCount').textContent = catalogMode === 'groups' ? `${rows.length} เมนู` : `${rows.length} สินค้า`;
    $('#productGrid').innerHTML = slots.map((row, index) => {
      const slot = firstPosition + index;
      if (!row) return `<span class="pos-button-empty-slot" aria-hidden="true" data-slot="${slot}"></span>`;
      if (catalogMode === 'groups') {
        return `<button class="pos-menu-button" type="button" data-button-group="${row.id}" aria-label="เปิดเมนู ${escapeHtml(row.name_th)}">
          <strong>${escapeHtml(row.name_th)}</strong>
        </button>`;
      }
      return `<button class="pos-product-text-button" type="button" data-product-uuid="${row.product_uuid}" aria-label="เพิ่ม ${escapeHtml(row.name_th)} ราคา ${money(row.price_satang)}">
        <strong><span>${escapeHtml(row.name_th)}</span></strong><b>${money(row.price_satang)}</b>
      </button>`;
    }).join('');
    const pager = $('#catalogPager');
    pager.hidden = pageCount <= 1;
    $('#catalogPageLabel').textContent = `หน้า ${catalogPage.toLocaleString('th-TH')} / ${pageCount.toLocaleString('th-TH')}`;
    $('#catalogPreviousButton').disabled = catalogPage <= 1;
    $('#catalogNextButton').disabled = catalogPage >= pageCount;
    if (!rows.length) {
      const detail = catalogMode === 'groups'
        ? 'ผู้จัดการสามารถเพิ่มเมนูได้ที่ ตั้งค่าปุ่มขาย'
        : catalogMode === 'search'
          ? 'ลองค้นหาด้วยชื่อ บาร์โค้ด หรือ SKU'
          : 'เมนูนี้ยังไม่ได้ตั้งค่าสินค้า';
      $('#productGrid').innerHTML = `<div class="empty-state"><span>▦</span><strong>ยังไม่มีรายการ</strong><p>${detail}</p></div>`;
    }
  }
  async function loadButtonGroups() {
    try {
      buttonGroups = await api('/api/pos/button-groups');
      products = [];
      currentGroup = null;
      catalogMode = 'groups';
      catalogPage = 1;
      renderCatalog();
    } catch (error) { message(error.message, true); }
  }
  async function loadButtonGroup(groupId) {
    try {
      const result = await api(`/api/pos/button-groups/${groupId}/products`);
      currentGroup = result.group;
      products = result.products;
      catalogMode = 'group';
      catalogPage = 1;
      renderCatalog();
    } catch (error) { message(error.message, true); }
  }
  async function loadSearchResults() {
    const value = $('#productLookup').value.trim();
    if (!value) {
      await loadButtonGroups();
      return;
    }
    try {
      products = await api(`/api/pos/products?q=${encodeURIComponent(value)}`);
      currentGroup = null;
      catalogMode = 'search';
      catalogPage = 1;
      renderCatalog();
    } catch (error) { message(error.message, true); }
  }
  async function refreshCatalog() {
    if ($('#productLookup').value.trim()) await loadSearchResults();
    else if (currentGroup && catalogMode === 'group') await loadButtonGroup(currentGroup.id);
    else await loadButtonGroups();
  }
  function openManualPrice(product, barcode, reason) {
    if (manualPriceDialog.open || manualPriceSaving) return;
    const normalizedBarcode = String(barcode || product?.barcode || '').trim();
    manualPriceContext = { product: product || null, barcode: normalizedBarcode, reason };
    $('#manualPriceProductName').textContent = reason === 'manual_price_barcode'
      ? 'รายการระบุราคาเอง'
      : product?.name_th || 'ไม่พบสินค้าในระบบ';
    $('#manualPriceBarcode').textContent = `บาร์โค้ด ${normalizedBarcode}`;
    $('#manualPriceInput').value = '';
    $('#manualPriceError').textContent = '';
    $('#manualPriceSubmit').disabled = false;
    manualPriceDialog.showModal();
    playManualPriceAlert(reason === 'manual_price_barcode');
    setTimeout(() => $('#manualPriceInput').focus({ preventScroll: true }), 40);
  }
  function addProduct(product, manualPrice = null) {
    if (!product) return;
    if (!manualPrice && (Number(product.price_satang) <= 0 || product.barcode === manualBarcode)) {
      openManualPrice(
        product,
        product.barcode,
        product.barcode === manualBarcode ? 'manual_price_barcode' : 'zero_catalog_price',
      );
      return;
    }
    const effectivePrice = manualPrice?.price_satang ?? product.price_satang;
    const reference = manualPrice?.reference || '';
    const item = cart.find((row) => (
      row.product_uuid === product.product_uuid
      && (row.manual_price_reference || '') === reference
    ));
    if (item) item.quantity += 1;
    else cart.push({
      product_uuid: product.product_uuid,
      name: product.name_th,
      price_satang: effectivePrice,
      manual_price_satang: manualPrice?.price_satang ?? null,
      manual_price_reference: reference || null,
      manual_price_reason: manualPrice?.reason || null,
      quantity: 1,
      discount_satang: 0,
      allow_decimal: product.allow_decimal_quantity,
    });
    renderCart();
    message(reference ? `เพิ่มรายการ ${reference} แล้ว` : `เพิ่ม ${product.name_th} แล้ว`);
    $('#productLookup').select();
  }
  async function addFromLookup({ scanner = false } = {}) {
    const value = $('#productLookup').value.trim();
    if (!value) return;
    if (value.toUpperCase() === manualBarcode) {
      openManualPrice(null, manualBarcode, 'manual_price_barcode');
      return;
    }
    try {
      const exactRows = await api(`/api/pos/products?barcode=${encodeURIComponent(value)}`);
      if (exactRows.length) {
        addProduct(exactRows[0]);
        $('#productLookup').value = '';
        if (!manualPriceDialog.open) await refreshCatalog();
        return;
      }
      const matching = await api(`/api/pos/products?q=${encodeURIComponent(value)}`);
      if (matching.length === 1) {
        addProduct(matching[0]);
        $('#productLookup').value = '';
        if (!manualPriceDialog.open) await refreshCatalog();
      } else {
        products = matching;
        currentGroup = null;
        catalogMode = 'search';
        catalogPage = 1;
        renderCatalog();
        const looksLikeBarcode = /^[A-Za-z0-9][A-Za-z0-9._/-]{2,127}$/.test(value);
        if (!matching.length && (scanner || looksLikeBarcode)) {
          message('ไม่พบสินค้า กรุณาระบุราคา', true);
          openManualPrice(null, value, 'missing_product');
        } else {
          message(matching.length ? 'เลือกสินค้าจากผลการค้นหา' : 'ไม่พบสินค้านี้', !matching.length);
        }
      }
    } catch (error) { message(error.message, true); }
    finally { if (!manualPriceDialog.open) $('#productLookup').focus(); }
  }
  async function quote() {
    if (!cart.length) {
      total = 0;
      updateTotals();
      $('#payButton').disabled = true;
      return;
    }
    try {
      const result = await api('/api/pos/quote', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items: cart, bill_discount_satang: 0 }) });
      total = result.total_satang;
      updateTotals();
      $('#payButton').disabled = false;
    } catch (error) { message(error.message, true); $('#payButton').disabled = true; }
  }
  function updateTotals() {
    $('#cartTotal').textContent = money(total);
    $('#mobileCartTotal').textContent = money(total);
    const units = cart.reduce((sum, row) => sum + Number(row.quantity), 0);
    const countText = `${units.toLocaleString('th-TH')} รายการ`;
    $('#cartCount').textContent = countText;
    $('#mobileCartCount').textContent = units.toLocaleString('th-TH');
    $('#mobileCartBar').classList.toggle('has-items', cart.length > 0);
  }
  function renderCart() {
    $('#cartItems').innerHTML = cart.map((item, index) => `
      <article class="cart-row-v2">
        <div class="cart-row-main"><strong>${escapeHtml(item.name)}</strong>${item.manual_price_reference ? `<small>${escapeHtml(item.manual_price_reference)}</small>` : ''}<span>${money(item.price_satang)} × ${item.quantity}</span></div>
        <strong class="line-total">${money(item.price_satang * item.quantity - item.discount_satang)}</strong>
        <div class="quantity-v2"><button type="button" data-action="minus" data-i="${index}" aria-label="ลดจำนวน">−</button><input aria-label="จำนวน ${escapeHtml(item.name)}" data-action="qty" data-i="${index}" type="number" min="${item.allow_decimal ? '.001' : '1'}" step="${item.allow_decimal ? '.001' : '1'}" value="${item.quantity}"><button type="button" data-action="plus" data-i="${index}" aria-label="เพิ่มจำนวน">+</button></div>
        <div class="row-tools"><button class="remove" type="button" data-action="remove" data-i="${index}">ลบ</button></div>
      </article>`).join('') || '<div class="empty-cart"><span>▧</span><strong>ตะกร้ายังว่าง</strong><p>สแกนบาร์โค้ดหรือเลือกสินค้าด้านซ้าย</p></div>';
    quote();
  }
  function updateCash() {
    const received = Math.round((Number($('#receivedInput').value) || 0) * 100);
    const change = received - total;
    $('#changeAmount').textContent = money(Math.max(0, change));
    $('#paymentError').textContent = received && received < total ? `ยังขาดอีก ${money(total - received)}` : '';
    $('#completeSaleButton').disabled = completing || (paymentMethod === 'cash' && received < total) || (paymentMethod === 'billing' && !$('#billingCustomer').value);
    const breakdown = [];
    if (received === total && total > 0) breakdown.push('ชำระเงินพอดี');
    let left = Math.floor(Math.max(0, change) / 100);
    [1000, 500, 100, 50, 20, 10, 5, 2, 1].forEach((value) => { const count = Math.floor(left / value); if (count) { breakdown.push(`${value >= 20 ? 'ธนบัตร' : 'เหรียญ'} ${value} บาท × ${count}`); left %= value; } });
    $('#changeBreakdown').innerHTML = breakdown.map((row) => `<span>${row}</span>`).join('');
  }
  function setMethod(method) {
    paymentMethod = method;
    document.querySelectorAll('.payment-tabs button').forEach((button) => { const active = button.dataset.method === method; button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active)); });
    $('#cashPanel').hidden = method !== 'cash';
    $('#confirmationPanel').hidden = !['scan', 'transfer'].includes(method);
    $('#billingPanel').hidden = method !== 'billing';
    $('#completeSaleButton').textContent = method === 'cash' ? 'ยืนยันรับเงินและจบการขาย' : method === 'billing' ? 'ยืนยันการวางบิล' : 'ยืนยันว่าได้รับเงินแล้ว';
    updateCash();
  }
  function openPayment() {
    const units = cart.reduce((sum, row) => sum + Number(row.quantity), 0);
    $('#paymentItemCount').textContent = `จำนวนสินค้า ${units.toLocaleString('th-TH')} ชิ้น`;
    $('#amountDue').textContent = money(total);
    $('#scanAmount').textContent = money(total);
    $('#billingAmount').textContent = money(total);
    $('#receivedInput').value = '0';
    setMethod('cash');
    updateCash();
    closeMobileCart();
    $('#paymentDialog').showModal();
    setTimeout(() => $('#receivedInput').focus(), 50);
  }
  async function complete() {
    if (completing) return;
    completing = true;
    updateCash();
    const button = $('#completeSaleButton');
    const original = button.textContent;
    button.textContent = 'กำลังบันทึก…';
    try {
      const reviewItems = cart.map((row) => ({ ...row })), reviewTotal = total;
      const payload = { items: cart, bill_discount_satang: 0, customer_note: $('#customerNote').value, payment_method: paymentMethod, amount_received_satang: Math.round((Number($('#receivedInput').value) || 0) * 100), payment_confirmed: paymentMethod === 'scan', billing_customer_id: $('#billingCustomer').value, billing_note: $('#billingNote').value };
      const result = await api('/api/pos/complete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      $('#successReceipt').textContent = result.receipt_number;
      $('#successItems').innerHTML = reviewItems.map((item) => `<div><span>${escapeHtml(item.manual_price_reference ? `รายการระบุราคา ${item.manual_price_reference}` : item.name)} × ${item.quantity}</span><strong>${money(item.price_satang * item.quantity - item.discount_satang)}</strong></div>`).join('');
      $('#successTotal').textContent = money(reviewTotal);
      $('#successChange').textContent = paymentMethod === 'cash' ? money(result.change_satang) : '—';
      const manualReceiptLink = $('#manualReceiptLink');
      if (result.print_queued) {
        $('#printStatus').textContent = 'บันทึกการขายและส่งใบเสร็จไปยังเครื่องพิมพ์แล้ว';
        manualReceiptLink.hidden = true;
      } else {
        $('#printStatus').textContent = 'บันทึกการขายแล้ว — ไม่พบตัวช่วยพิมพ์อัตโนมัติ';
        manualReceiptLink.href = result.receipt_url;
        manualReceiptLink.hidden = false;
      }
      cart = [];
      $('#billDiscount').value = 0;
      $('#customerNote').value = '';
      renderCart();
      $('#paymentDialog').close();
      $('#saleSuccessDialog').showModal();
      $('#productLookup').value = '';
      await loadButtonGroups();
    } catch (error) { $('#paymentError').textContent = error.message; }
    finally { completing = false; button.textContent = original; updateCash(); }
  }
  function openMobileCart() { document.body.classList.add('mobile-cart-open'); $('#cartPanel').setAttribute('aria-hidden', 'false'); }
  function closeMobileCart() { document.body.classList.remove('mobile-cart-open'); }

  $('#productGrid').addEventListener('click', (event) => {
    const groupButton = event.target.closest('[data-button-group]');
    if (groupButton) {
      loadButtonGroup(groupButton.dataset.buttonGroup);
      return;
    }
    const productButton = event.target.closest('[data-product-uuid]');
    if (productButton) addProduct(products.find((product) => product.product_uuid === productButton.dataset.productUuid));
  });
  $('#catalogBackButton').onclick = () => {
    $('#productLookup').value = '';
    loadButtonGroups();
    $('#productLookup').focus();
  };
  $('#catalogPreviousButton').onclick = () => { catalogPage = Math.max(1, catalogPage - 1); renderCatalog(); };
  $('#catalogNextButton').onclick = () => { catalogPage = Math.min(catalogPageCount(), catalogPage + 1); renderCatalog(); };
  $('#cartItems').addEventListener('change', (event) => { const index = Number(event.target.dataset.i); if (event.target.dataset.action === 'qty') cart[index].quantity = Math.max(Number(event.target.min), Number(event.target.value) || 1); renderCart(); });
  $('#cartItems').addEventListener('click', (event) => { const button = event.target.closest('[data-action]'); if (!button || button.tagName === 'INPUT') return; const index = Number(button.dataset.i); if (button.dataset.action === 'plus') cart[index].quantity += 1; if (button.dataset.action === 'minus') cart[index].quantity -= 1; if (button.dataset.action === 'remove' || cart[index]?.quantity <= 0) cart.splice(index, 1); renderCart(); });
  document.addEventListener('keydown', receiveScannerKey, true);
  $('#productLookup').addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); clearTimeout(searchTimer); addFromLookup(); } });
  $('#productLookup').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadSearchResults, 250); });
  $('#addLookupButton').onclick = addFromLookup;
  $('#clearLookup').onclick = () => { $('#productLookup').value = ''; loadButtonGroups(); $('#productLookup').focus(); };
  $('#payButton').onclick = openPayment;
  document.querySelectorAll('.payment-tabs button').forEach((button) => button.onclick = () => setMethod(button.dataset.method));
  document.querySelectorAll('[data-denom]').forEach((button) => button.onclick = () => { $('#receivedInput').value = (Number($('#receivedInput').value) || 0) + Number(button.dataset.denom); updateCash(); });
  $('#clearReceivedButton').onclick = () => { $('#receivedInput').value = '0'; updateCash(); $('#receivedInput').focus(); };
  $('#exactButton').onclick = () => { $('#receivedInput').value = Math.round(total / 100); updateCash(); };
  $('#receivedInput').oninput = updateCash;
  $('#billingCustomer').onchange = updateCash;
  $('#completeSaleButton').onclick = complete;
  $('#closeSuccessButton').onclick = () => { $('#saleSuccessDialog').close(); $('#productLookup').focus(); };
  $('#holdButton').onclick = async () => { if (!cart.length) return; const label = prompt('ชื่อบิลที่พักไว้', 'บิลพัก'); if (!label) return; await api('/api/pos/held', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ label, cart: { items: cart, bill_discount: 0, note: $('#customerNote').value } }) }); cart = []; renderCart(); closeMobileCart(); message('พักบิลแล้ว'); };
  $('#heldButton').onclick = async () => { const rows = await api('/api/pos/held'); $('#heldList').innerHTML = rows.map((row) => `<button class="held-row" type="button" data-held="${row.id}" data-cart="${encodeURIComponent(row.cart_json)}"><strong>${escapeHtml(row.label)}</strong><span>${row.updated_at}</span></button>`).join('') || '<p class="empty">ไม่มีบิลที่พักไว้</p>'; $('#heldDialog').showModal(); };
  $('#heldList').onclick = async (event) => { const button = event.target.closest('[data-held]'); if (!button) return; const saved = JSON.parse(decodeURIComponent(button.dataset.cart)); cart = saved.items.map((item) => ({ ...item, discount_satang: 0 })); $('#billDiscount').value = 0; $('#customerNote').value = saved.note; await api(`/api/pos/held/${button.dataset.held}`, { method: 'DELETE' }); renderCart(); $('#heldDialog').close(); };
  $('#mobileCartBar').onclick = openMobileCart;
  $('#closeMobileCart').onclick = closeMobileCart;
  $('#cartBackdrop').onclick = closeMobileCart;
  manualPriceDialog.addEventListener('cancel', (event) => event.preventDefault());
  $('#manualPriceNumpad').addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button || manualPriceSaving) return;
    const input = $('#manualPriceInput');
    const current = input.value.replace(/\D/g, '');
    if (button.dataset.manualPriceKey !== undefined) {
      input.value = `${current}${button.dataset.manualPriceKey}`.slice(0, 7);
    } else if (button.dataset.manualPriceAction === 'backspace') {
      input.value = current.slice(0, -1);
    } else if (button.dataset.manualPriceAction === 'clear') {
      input.value = '';
    }
    $('#manualPriceError').textContent = '';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus({ preventScroll: true });
  });
  $('#manualPriceForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!manualPriceContext || manualPriceSaving) return;
    manualPriceSaving = true;
    $('#manualPriceSubmit').disabled = true;
    $('#manualPriceError').textContent = '';
    try {
      const result = await api('/api/pos/manual-price', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          barcode: manualPriceContext.barcode,
          price_baht: $('#manualPriceInput').value,
        }),
      });
      const product = result.product;
      const manualPrice = result.uses_catalog_price ? null : {
        price_satang: result.manual_price_satang,
        reference: result.manual_price_reference,
        reason: result.manual_price_reason,
      };
      manualPriceDialog.close();
      manualPriceContext = null;
      addProduct(product, manualPrice);
      $('#productLookup').value = '';
      await refreshCatalog();
      $('#productLookup').focus({ preventScroll: true });
      $('#productLookup').select();
    } catch (error) {
      $('#manualPriceError').textContent = error.message;
      $('#manualPriceInput').focus({ preventScroll: true });
      $('#manualPriceInput').select();
    } finally {
      manualPriceSaving = false;
      $('#manualPriceSubmit').disabled = false;
    }
  });
  window.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMobileCart(); });
  loadButtonGroups();
  renderCart();
})();
