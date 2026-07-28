(() => {
  const app = document.querySelector('#posApp');
  if (!app) return;
  const $ = (selector) => document.querySelector(selector);
  const csrf = app.dataset.csrf;
  const money = (satang) => `${Math.round(satang / 100).toLocaleString('th-TH')} บาท`;
  const escapeHtml = (text) => { const node = document.createElement('div'); node.textContent = text || ''; return node.innerHTML; };
  let products = [], cart = [], total = 0, paymentMethod = 'cash', activeCategory = '', completing = false, searchTimer;

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
  async function loadProducts() {
    try {
      const query = encodeURIComponent($('#productLookup').value.trim());
      products = await api(`/api/pos/products?q=${query}&category_id=${activeCategory}`);
      renderProducts();
    } catch (error) { message(error.message, true); }
  }
  function renderProducts() {
    $('#resultCount').textContent = `${products.length} สินค้า`;
    $('#productGrid').innerHTML = products.map((product) => `
      <button class="product-card-v2" type="button" data-product-uuid="${product.product_uuid}" aria-label="เพิ่ม ${escapeHtml(product.name_th)} ราคา ${money(product.price_satang)}">
        ${product.image_path ? `<img src="/uploads/products/${encodeURIComponent(product.image_path)}" alt="">` : '<span class="product-placeholder-v2" aria-hidden="true">□</span>'}
        <span class="product-info-v2"><strong>${escapeHtml(product.name_th)}</strong><b>${money(product.price_satang)}</b></span>
      </button>`).join('') || '<div class="empty-state"><span>⌕</span><strong>ไม่พบสินค้า</strong><p>ลองค้นหาด้วยชื่อ บาร์โค้ด หรือเลือกหมวดอื่น</p></div>';
  }
  function addProduct(product) {
    const item = cart.find((row) => row.product_uuid === product.product_uuid);
    if (item) item.quantity += 1;
    else cart.push({ product_uuid: product.product_uuid, name: product.name_th, price_satang: product.price_satang, quantity: 1, discount_satang: 0, allow_decimal: product.allow_decimal_quantity });
    renderCart();
    message(`เพิ่ม ${product.name_th} แล้ว`);
    $('#productLookup').select();
  }
  async function addFromLookup() {
    const value = $('#productLookup').value.trim();
    if (!value) return;
    try {
      const exactRows = await api(`/api/pos/products?barcode=${encodeURIComponent(value)}`);
      if (exactRows.length) {
        addProduct(exactRows[0]);
        $('#productLookup').value = '';
        await loadProducts();
        return;
      }
      const matching = await api(`/api/pos/products?q=${encodeURIComponent(value)}&category_id=${activeCategory}`);
      if (matching.length === 1) {
        addProduct(matching[0]);
        $('#productLookup').value = '';
        await loadProducts();
      } else {
        products = matching;
        renderProducts();
        message(matching.length ? 'เลือกสินค้าจากผลการค้นหา' : 'ไม่พบสินค้านี้', !matching.length);
      }
    } catch (error) { message(error.message, true); }
    finally { $('#productLookup').focus(); }
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
        <div class="cart-row-main"><strong>${escapeHtml(item.name)}</strong><span>${money(item.price_satang)} × ${item.quantity}</span></div>
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
      $('#successItems').innerHTML = reviewItems.map((item) => `<div><span>${escapeHtml(item.name)} × ${item.quantity}</span><strong>${money(item.price_satang * item.quantity - item.discount_satang)}</strong></div>`).join('');
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
      await loadProducts();
    } catch (error) { $('#paymentError').textContent = error.message; }
    finally { completing = false; button.textContent = original; updateCash(); }
  }
  function openMobileCart() { document.body.classList.add('mobile-cart-open'); $('#cartPanel').setAttribute('aria-hidden', 'false'); }
  function closeMobileCart() { document.body.classList.remove('mobile-cart-open'); }

  $('#productGrid').addEventListener('click', (event) => { const button = event.target.closest('[data-product-uuid]'); if (button) addProduct(products.find((product) => product.product_uuid === button.dataset.productUuid)); });
  $('#categoryBoxes').addEventListener('click', (event) => { const button = event.target.closest('[data-category]'); if (!button) return; activeCategory = button.dataset.category; document.querySelectorAll('.category-chip').forEach((chip) => chip.classList.toggle('active', chip === button)); loadProducts(); });
  $('#cartItems').addEventListener('change', (event) => { const index = Number(event.target.dataset.i); if (event.target.dataset.action === 'qty') cart[index].quantity = Math.max(Number(event.target.min), Number(event.target.value) || 1); renderCart(); });
  $('#cartItems').addEventListener('click', (event) => { const button = event.target.closest('[data-action]'); if (!button || button.tagName === 'INPUT') return; const index = Number(button.dataset.i); if (button.dataset.action === 'plus') cart[index].quantity += 1; if (button.dataset.action === 'minus') cart[index].quantity -= 1; if (button.dataset.action === 'remove' || cart[index]?.quantity <= 0) cart.splice(index, 1); renderCart(); });
  $('#productLookup').addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); clearTimeout(searchTimer); addFromLookup(); } });
  $('#productLookup').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadProducts, 250); });
  $('#addLookupButton').onclick = addFromLookup;
  $('#clearLookup').onclick = () => { $('#productLookup').value = ''; loadProducts(); $('#productLookup').focus(); };
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
  window.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMobileCart(); });
  loadProducts();
  renderCart();
})();
