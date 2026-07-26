(() => {
  const cart=(()=>{try{return JSON.parse(localStorage.getItem("onlineCartV1")||"[]")}catch{return[]}})();
  const message=document.querySelector("#checkoutMessage"),locationSelect=document.querySelector("#deliveryLocation"),submit=document.querySelector("#submitOrder"),payment=document.querySelector("#paymentMethod");
  const steps={delivery:document.querySelector("#deliveryStep"),payment:document.querySelector("#paymentStep"),confirm:document.querySelector("#confirmStep")};
  const titles={delivery:["ขั้นตอน 1 จาก 3","รายละเอียดการจัดส่ง"],payment:["ขั้นตอน 2 จาก 3","วิธีชำระเงิน"],confirm:["ขั้นตอน 3 จาก 3","ตรวจสอบและยืนยันออเดอร์"]};
  let subtotal=0,validated=false,accountExists=false,inlineLoggedIn=false,idempotency=sessionStorage.getItem("onlineOrderKey")||(crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`);
  sessionStorage.setItem("onlineOrderKey",idempotency);
  const popup=text=>{message.textContent=text;message.classList.add("show");setTimeout(()=>message.classList.remove("show"),3500)};
  const money=satang=>(satang/100).toFixed(2)+" บาท";
  const clearInvalid=field=>{field?.classList.remove("field-invalid");field?.removeAttribute("aria-invalid")};
  const markInvalid=field=>{if(!field)return;field.classList.add("field-invalid");field.setAttribute("aria-invalid","true")};
  function failField(field,text){markInvalid(field);field.scrollIntoView({behavior:"smooth",block:"center"});field.focus();popup(text);return false}
  function deliveryFee(){const option=locationSelect.selectedOptions[0],rawFee=Number(option?.dataset.fee||0);return subtotal>=10000?0:rawFee}
  async function validate(){
    const response=await fetch("/order/api/cart/validate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items:cart.map(x=>({product_id:x.product_id,quantity:x.quantity}))})}),data=await response.json();
    if(!response.ok){popup(data.error);submit.disabled=true;return}
    validated=true;subtotal=data.subtotal_satang;
    document.querySelector("#checkoutItems").innerHTML=data.items.map(x=>`<div class="checkout-row"><span>${x.name_th} × ${x.quantity}</span><strong>${money(x.line_total_satang)}</strong></div>`).join("");
    document.querySelector("#checkoutSubtotal").textContent=money(subtotal);
    const remain=Math.max(0,10000-subtotal);document.querySelector("#freeShippingProgress").value=Math.min(subtotal,10000);document.querySelector("#freeShippingText").textContent=remain?`อีก ${money(remain)} ฟรีค่าส่ง`:"ครบยอดฟรีค่าส่งแล้ว";update()
  }
  function update(){
    const fee=deliveryFee(),option=locationSelect.selectedOptions[0];
    document.querySelector("#deliveryFee").textContent=money(fee);document.querySelector("#grandTotal").textContent=money(subtotal+fee);
    document.querySelector("#roomReference").required=option?.dataset.roomRequired==="1";
    document.querySelector("#cashExpectedLabel").hidden=payment.value!=="cash"
  }
  function showStep(name){
    Object.entries(steps).forEach(([key,section])=>{section.hidden=key!==name;section.classList.toggle("active",key===name)});
    const index={delivery:0,payment:1,confirm:2}[name];document.querySelectorAll(".checkout-stepper i").forEach((dot,i)=>dot.classList.toggle("active",i<=index));
    document.querySelector("#stepEyebrow").textContent=titles[name][0];document.querySelector("#stepTitle").textContent=titles[name][1];scrollTo({top:0,behavior:"smooth"})
  }
  function deliveryValid(){
    const phone=document.querySelector("#guestPhone"),name=document.querySelector("#guestName");
    if(phone&&!phone.value.trim())return failField(phone,"กรุณาระบุเบอร์มือถือ");
    if(name?.required&&!name.value.trim())return failField(name,"กรุณาระบุชื่อผู้สั่ง");
    if(!locationSelect.value)return failField(locationSelect,"กรุณาเลือกสถานที่จัดส่ง");
    const room=document.querySelector("#roomReference");if(room.required&&!room.value.trim())return failField(room,"กรุณาระบุห้องหรือจุดรับ");
    if(document.querySelector("#saveAccount")?.checked&&document.querySelector("#newPin").value.length!==4)return failField(document.querySelector("#newPin"),"กรุณาตั้ง PIN ให้ครบ 4 หลัก");
    return true
  }
  async function lookupAccount(){
    const phone=document.querySelector("#guestPhone");if(!phone||phone.value.replace(/\D/g,"").length<10)return false;
    const response=await fetch("/order/api/account/lookup",{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":document.querySelector("#customerCsrf").value},body:JSON.stringify({phone:phone.value})}),data=await response.json();
    if(!response.ok){markInvalid(phone);popup(data.error);return null}
    accountExists=data.account_exists;
    document.querySelector("#existingAccountPanel").hidden=!accountExists||inlineLoggedIn;
    document.querySelector("#newAccountOffer").hidden=accountExists||inlineLoggedIn;
    document.querySelector("#guestNameLabel").hidden=accountExists||inlineLoggedIn;
    document.querySelector("#guestName").required=!accountExists&&!inlineLoggedIn;
    return accountExists
  }
  async function inlineLogin(){
    const pin=document.querySelector("#existingPin");if(pin.value.length!==4)return failField(pin,"กรุณากรอก PIN ให้ครบ 4 หลัก");
    const response=await fetch("/order/api/account/login",{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":document.querySelector("#customerCsrf").value},body:JSON.stringify({phone:document.querySelector("#guestPhone").value,pin:pin.value})}),data=await response.json();
    if(!response.ok){markInvalid(pin);return popup(data.error)}
    inlineLoggedIn=true;document.querySelector("#customerCsrf").value=data.csrf_token;document.querySelector("#existingAccountPanel").hidden=true;document.querySelector("#guestNameLabel").hidden=true;document.querySelector("#guestName").required=false;popup("เข้าสู่บัญชีเดิมแล้ว")
  }
  function renderConfirmation(){
    const option=locationSelect.selectedOptions[0],fee=deliveryFee(),cash=document.querySelector("#cashExpected").value;
    document.querySelector("#confirmationSummary").innerHTML=`<h2>สรุปออเดอร์</h2><div class="confirm-block"><span>จัดส่งที่</span><strong>${option.textContent}${document.querySelector("#roomReference").value?` · ${document.querySelector("#roomReference").value}`:""}</strong></div><div class="confirm-block"><span>วิธีชำระเงิน</span><strong>${payment.selectedOptions[0].textContent}</strong>${payment.value==="cash"&&cash?`<small>เตรียมเงินทอนจาก ${Number(cash).toFixed(2)} บาท</small>`:""}</div><div class="confirm-total"><span>รวมทั้งหมด</span><strong>${money(subtotal+fee)}</strong></div>`
  }
  document.querySelectorAll("#checkoutForm input,#checkoutForm select,#checkoutForm textarea").forEach(field=>{field.addEventListener("input",()=>clearInvalid(field));field.addEventListener("change",()=>clearInvalid(field))});
  locationSelect.addEventListener("change",update);payment.addEventListener("change",update);
  document.querySelector("#saveAccount")?.addEventListener("change",e=>document.querySelector("#newPinWrap").hidden=!e.target.checked);
  document.querySelector(".guest-pin-pad")?.addEventListener("click",e=>{const button=e.target.closest("button"),pin=document.querySelector("#newPin");if(!button)return;if(button.dataset.value!==undefined)pin.value=(pin.value+button.dataset.value).slice(0,4);if(button.dataset.action==="clear")pin.value="";if(button.dataset.action==="back")pin.value=pin.value.slice(0,-1)});
  document.querySelector(".existing-pin-pad")?.addEventListener("click",e=>{const button=e.target.closest("button"),pin=document.querySelector("#existingPin");if(!button)return;if(button.dataset.value!==undefined)pin.value=(pin.value+button.dataset.value).slice(0,4);if(button.dataset.action==="clear")pin.value="";if(button.dataset.action==="back")pin.value=pin.value.slice(0,-1)});
  document.querySelector("#guestPhone")?.addEventListener("blur",lookupAccount);
  document.querySelector("#inlineLoginButton")?.addEventListener("click",inlineLogin);
  document.querySelector("#toPayment").addEventListener("click",async()=>{if(document.querySelector("#guestPhone")&&!inlineLoggedIn){const exists=await lookupAccount();if(exists===null)return;if(exists)return failField(document.querySelector("#existingPin"),"กรุณากรอก PIN ของบัญชีเดิม")}if(deliveryValid())showStep("payment")});
  document.querySelector("#toConfirm").addEventListener("click",()=>{renderConfirmation();showStep("confirm")});
  document.querySelectorAll(".step-back").forEach(button=>button.addEventListener("click",()=>showStep(button.dataset.step)));
  submit.addEventListener("click",async()=>{
    if(!validated||!deliveryValid())return;
    const room=document.querySelector("#roomReference");submit.disabled=true;popup("กำลังส่งออเดอร์...");
    const payload={items:cart.map(x=>({product_id:x.product_id,quantity:x.quantity})),delivery_location_id:Number(locationSelect.value),room_reference:room.value,payment_method:payment.value,customer_note:document.querySelector("#customerNote").value,cash_expected_satang:payment.value==="cash"?Math.round(Number(document.querySelector("#cashExpected").value||0)*100):0,idempotency_key:idempotency,phone:inlineLoggedIn?undefined:document.querySelector("#guestPhone")?.value,display_name:inlineLoggedIn?undefined:document.querySelector("#guestName")?.value,new_pin:inlineLoggedIn?"":document.querySelector("#saveAccount")?.checked?document.querySelector("#newPin")?.value:""};
    try{const response=await fetch("/order/api/orders",{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":document.querySelector("#customerCsrf").value},body:JSON.stringify(payload)}),data=await response.json();if(!response.ok)throw new Error(data.error);localStorage.removeItem("onlineCartV1");sessionStorage.removeItem("onlineOrderKey");window.location.href=data.detail_url}catch(error){popup(error.message);submit.disabled=false}
  });
  validate().catch(()=>{popup("ไม่สามารถตรวจสอบตะกร้าได้");submit.disabled=true});
})();
