(() => {
  const key="onlineCartV1";
  const read=()=>{try{return JSON.parse(localStorage.getItem(key)||"[]")}catch{return[]}};
  const write=cart=>{localStorage.setItem(key,JSON.stringify(cart));updateCount()};
  function updateCount(){document.querySelector("#cartCount").textContent=read().reduce((sum,item)=>sum+item.quantity,0).toFixed(0)}
  function add(product,button){
    const cart=read(),item=cart.find(row=>row.product_id===product.id),step=product.allow_decimal_quantity?0.001:1,next=(item?.quantity||0)+step,max=Math.min(product.available_quantity,product.online_max_quantity||Infinity);
    if(next>max)return;
    if(item)item.quantity=next;else cart.push({product_id:product.id,name_th:product.name_th,image_path:product.image_path||"",price_satang:product.price_satang,quantity:step,max,allow_decimal_quantity:product.allow_decimal_quantity});
    write(cart);button.classList.add("added");setTimeout(()=>button.classList.remove("added"),450);
    const toast=document.querySelector("#cartToast");toast.textContent=`เพิ่ม ${product.name_th} ลงตะกร้าแล้ว`;toast.classList.add("show");setTimeout(()=>toast.classList.remove("show"),1800)
  }
  document.querySelectorAll(".customer-product").forEach(card=>card.querySelector(".add-product").addEventListener("click",event=>add(JSON.parse(card.dataset.product),event.currentTarget)));
  updateCount()
})();
