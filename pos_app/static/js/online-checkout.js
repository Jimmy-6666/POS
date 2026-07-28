(() => {
  const cart = (() => { try { return JSON.parse(localStorage.getItem("onlineCartV2") || "[]"); } catch { return []; } })();
  const $ = selector => document.querySelector(selector);
  const location = $("#deliveryLocation"), payment = $("#paymentMethod"), submit = $("#submitOrder");
  const popup = text => {
    $("#checkoutMessage").textContent = text;
    $("#checkoutMessage").classList.add("show");
    setTimeout(() => $("#checkoutMessage").classList.remove("show"), 3500);
  };
  const money = value => `${(value / 100).toFixed(2)} บาท`;
  let subtotal = 0, valid = false;
  const key = sessionStorage.getItem("onlineOrderKey") || (crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`);
  sessionStorage.setItem("onlineOrderKey", key);
  const fee = () => subtotal >= 10000 ? 0 : Number(location.selectedOptions[0]?.dataset.fee || 0);
  const refresh = () => {
    $("#deliveryFee").textContent = money(fee());
    $("#grandTotal").textContent = money(subtotal + fee());
    $("#roomReference").required = location.selectedOptions[0]?.dataset.roomRequired === "1";
    $("#cashExpectedLabel").hidden = payment.value !== "cash";
  };
  const fieldsValid = () => {
    const checks = [
      ["#contactName", "กรุณาระบุชื่อสำหรับติดต่อ"],
      ["#contactPhone", "กรุณาระบุเบอร์มือถือ"],
      ["#deliveryLocation", "กรุณาเลือกสถานที่จัดส่ง"],
    ];
    if ($("#roomReference").required) checks.push(["#roomReference", "กรุณาระบุห้องหรือจุดรับ"]);
    for (const [selector, message] of checks) {
      const field = $(selector);
      if (!field.value.trim()) { field.focus(); popup(message); return false; }
    }
    return true;
  };
  const textNode = (tag, text) => {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  };
  const block = (label, value, extra) => {
    const node = document.createElement("div");
    node.className = "confirm-block";
    node.append(textNode("span", label), textNode("strong", value));
    if (extra) node.append(extra);
    return node;
  };
  const summary = () => {
    const option = location.selectedOptions[0], cash = $("#cashExpected").value;
    const host = $("#confirmationSummary");
    const preparedCash = payment.value === "cash" && cash ? textNode("small", `เตรียมเงิน ${Number(cash).toFixed(2)} บาท`) : null;
    const total = document.createElement("div");
    total.className = "confirm-total";
    total.append(textNode("span", "รวมทั้งหมด"), textNode("strong", money(subtotal + fee())));
    host.replaceChildren(
      textNode("h2", "สรุปออเดอร์"),
      block("ผู้ติดต่อ", `${$("#contactName").value} · ${$("#contactPhone").value}`),
      block("จัดส่ง", `${option.textContent}${$("#roomReference").value ? ` · ${$("#roomReference").value}` : ""}`),
      block("การชำระเงิน", payment.selectedOptions[0].textContent, preparedCash),
      total,
    );
  };
  async function loadCart() {
    const response = await fetch("/order/api/cart/validate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: cart.map(item => ({ product_uuid: item.product_uuid, quantity: item.quantity })) }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    subtotal = data.subtotal_satang;
    valid = true;
    $("#checkoutSubtotal").textContent = money(subtotal);
    refresh();
  }
  $("#toConfirm").addEventListener("click", () => {
    if (!valid || !fieldsValid()) return;
    summary();
    $("#deliveryStep").hidden = true;
    $("#confirmStep").hidden = false;
    $("#stepEyebrow").textContent = "ขั้นตอน 2 จาก 2";
    $("#stepTitle").textContent = "ตรวจสอบและยืนยันออเดอร์";
  });
  $("#editOrder").addEventListener("click", () => {
    $("#confirmStep").hidden = true;
    $("#deliveryStep").hidden = false;
    $("#stepEyebrow").textContent = "ขั้นตอน 1 จาก 2";
    $("#stepTitle").textContent = "ข้อมูลจัดส่งและการชำระเงิน";
  });
  location.addEventListener("change", refresh);
  payment.addEventListener("change", refresh);
  const savedList = $("#savedDeliveryList");
  let deliveryRows = [];
  $("#savedDeliveryButton").addEventListener("click", async () => {
    try {
      const rows = await (await fetch("/order/api/delivery-history")).json();
      savedList.replaceChildren();
      if (!rows.length) savedList.append(textNode("p", "ยังไม่มีข้อมูลจัดส่งเดิม"));
      rows.forEach((row, index) => {
        const button = document.createElement("button");
        button.className = "saved-delivery";
        button.type = "button";
        button.dataset.index = index;
        button.append(
          textNode("strong", row.contact_name),
          textNode("span", `${row.contact_phone} · ${row.location_name_snapshot} ${row.room_reference || ""}`.trim()),
        );
        savedList.append(button);
      });
      deliveryRows = rows;
      $("#savedDeliveryDialog").showModal();
    } catch { popup("ไม่สามารถโหลดข้อมูลจัดส่งเดิมได้"); }
  });
  savedList.addEventListener("click", event => {
    const button = event.target.closest("button[data-index]");
    if (!button) return;
    const row = deliveryRows[Number(button.dataset.index)];
    if (!row) return;
    $("#contactName").value = row.contact_name;
    $("#contactPhone").value = row.contact_phone;
    location.value = row.delivery_location_id;
    $("#roomReference").value = row.room_reference || "";
    refresh();
    $("#savedDeliveryDialog").close();
  });
  $("#closeSavedDelivery").addEventListener("click", () => $("#savedDeliveryDialog").close());
  submit.addEventListener("click", async () => {
    if (!valid || !fieldsValid()) return;
    submit.disabled = true;
    const payload = {
      items: cart.map(item => ({ product_uuid: item.product_uuid, quantity: item.quantity })),
      contact_name: $("#contactName").value,
      contact_phone: $("#contactPhone").value,
      delivery_location_id: Number(location.value),
      room_reference: $("#roomReference").value,
      payment_method: payment.value,
      customer_note: $("#customerNote").value,
      cash_expected_satang: payment.value === "cash" ? Math.round(Number($("#cashExpected").value || 0) * 100) : 0,
      idempotency_key: key,
    };
    try {
      const response = await fetch("/order/api/orders", {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": $("#customerCsrf").value },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      localStorage.removeItem("onlineCartV2");
      sessionStorage.removeItem("onlineOrderKey");
      window.location.href = data.detail_url;
    } catch (error) { popup(error.message); submit.disabled = false; }
  });
  loadCart().catch(error => {
    popup(error.message || "ไม่สามารถตรวจสอบตะกร้าได้");
    submit.disabled = true;
  });
})();
