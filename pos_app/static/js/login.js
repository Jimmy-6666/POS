(() => {
  const pin=document.querySelector('#loginPin'),pad=document.querySelector('.login-numpad');
  if(!pin||!pad)return;
  const update=value=>{pin.value=value.slice(0,Number(pin.dataset.pinLength||6));pin.dispatchEvent(new Event('input',{bubbles:true}))};
  pad.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.dataset.pinKey!==undefined)update(pin.value+button.dataset.pinKey);
    if(button.dataset.pinAction==='backspace')update(pin.value.slice(0,-1));
    if(button.dataset.pinAction==='clear')update('');
    pin.focus({preventScroll:true});
  });
})();
