(() => {
  const dialog = document.querySelector('#receiptPopup');
  const frame = document.querySelector('#receiptPopupFrame');
  if (!dialog || !frame) return;
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a.receipt-popup');
    if (!link) return;
    event.preventDefault();
    frame.src = link.href;
    dialog.showModal();
  });
  document.querySelector('#closeReceiptPopup').onclick = () => dialog.close();
  dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => { frame.src = 'about:blank'; });
})();
