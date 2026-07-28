(() => {
  const key="onlineCartV2",host=document.querySelector("#cartItems");
  const read=()=>{try{return JSON.parse(localStorage.getItem(key)||"[]")}catch{return[]}};
  const write=cart=>{localStorage.setItem(key,JSON.stringify(cart));render()};
  const escapeHtml=value=>{const node=document.createElement("div");node.textContent=value;return node.innerHTML};
  function add(product,button){
    const cart=read(),item=cart.find(row=>row.product_uuid===product.product_uuid),step=product.allow_decimal_quantity?0.001:1,max=product.max_quantity;
    if((item?.quantity||0)+step>max)return;
    if(item)item.quantity+=step;else cart.push({product_uuid:product.product_uuid,name_th:product.name_th,image_path:product.image_path||"",price_satang:product.price_satang,quantity:step,max,allow_decimal_quantity:product.allow_decimal_quantity});
    write(cart);button.classList.add("added");setTimeout(()=>button.classList.remove("added"),450)
  }
  function render(){
    const cart=read(),subtotal=cart.reduce((sum,item)=>sum+item.price_satang*item.quantity,0);
    host.innerHTML=cart.length?cart.map((item,index)=>`<article class="glass-cart-item">${item.image_path?`<img src="/order/products/${encodeURIComponent(item.image_path)}" alt="">`:`<div class="cart-image-placeholder">สินค้า</div>`}<div class="glass-cart-copy"><strong>${escapeHtml(item.name_th)}</strong><span>${(item.price_satang/100).toFixed(2)} บาท</span></div><button class="glass-cart-remove" data-remove="${index}" aria-label="ยกเลิก ${escapeHtml(item.name_th)}">×</button><div class="glass-quantity"><button data-minus="${index}" aria-label="ลดจำนวน">−</button><output>${item.quantity}</output><button data-plus="${index}" aria-label="เพิ่มจำนวน">+</button></div></article>`).join(""):`<div class="glass-empty"><strong>ตะกร้ายังว่าง</strong><p>เลือกสินค้าที่ต้องการแล้วกลับมาที่นี่</p><a class="primary" href="/order">เลือกสินค้า</a></div>`;
    document.querySelector("#cartSubtotal").textContent=(subtotal/100).toFixed(2)+" บาท";
    document.querySelector("#cartDeliveryHint").textContent=subtotal>=10000?"ครบยอดฟรีค่าส่งแล้ว":`อีก ${((10000-subtotal)/100).toFixed(2)} บาท ฟรีค่าส่ง`;
    document.querySelector("#checkoutLink").classList.toggle("disabled",!cart.length||document.body.dataset.orderingOpen!=="1")
  }
  async function hydrate(){
    const cart=read();if(!cart.length)return render();
    try{
      const response=await fetch("/order/api/cart/validate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items:cart.map(item=>({product_uuid:item.product_uuid,quantity:item.quantity}))})}),data=await response.json();
      if(!response.ok)return render();
      const current=new Map(data.items.map(item=>[item.product_uuid,item]));
      cart.forEach(item=>{const product=current.get(item.product_uuid);if(!product)return;item.image_path=product.image_path||item.image_path;item.price_satang=product.unit_price_satang;item.max=product.max_quantity});
      localStorage.setItem(key,JSON.stringify(cart));render()
    }catch{render()}
  }
  host.addEventListener("click",event=>{const cart=read(),target=event.target;for(const action of ["minus","plus","remove"]){if(target.dataset[action]===undefined)continue;const index=Number(target.dataset[action]);if(action==="remove")cart.splice(index,1);else{const step=cart[index].allow_decimal_quantity?0.001:1;cart[index].quantity=Math.max(step,Math.min(cart[index].max,cart[index].quantity+(action==="plus"?step:-step)))}write(cart)}});
  document.querySelectorAll(".customer-product").forEach(card=>card.querySelector(".add-product").addEventListener("click",event=>add(JSON.parse(card.dataset.product),event.currentTarget)));
  hydrate()
})();
