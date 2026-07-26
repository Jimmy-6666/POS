(() => {
  const selectors = [...document.querySelectorAll('.bill-selector')];
  const all = document.querySelector('#selectAllBills');
  if (!all) return;
  const money = (satang) => (satang / 100).toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const update = () => {
    const selected = selectors.filter((item) => item.checked);
    const sum = (key) => selected.reduce((total, item) => total + Number(item.dataset[key] || 0), 0);
    document.querySelector('#selectedOriginal').textContent = money(sum('original'));
    document.querySelector('#selectedPaid').textContent = money(sum('paid'));
    document.querySelector('#selectedBalance').textContent = money(sum('balance'));
    document.querySelector('#selectedCount').textContent = `${selected.length} รายการ`;
    document.querySelector('#bulkPaymentButton').disabled = !selected.length || sum('balance') <= 0;
    all.checked = selectors.length > 0 && selected.length === selectors.length;
    all.indeterminate = selected.length > 0 && selected.length < selectors.length;
  };
  all.addEventListener('change', () => { selectors.forEach((item) => { item.checked = all.checked; }); update(); });
  selectors.forEach((item) => item.addEventListener('change', update));
  update();
})();
