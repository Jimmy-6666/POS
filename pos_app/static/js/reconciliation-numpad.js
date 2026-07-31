(() => {
  const keypad = document.querySelector('#reconciliationNumpad');
  if (!keypad) return;
  const inputs = Array.from(document.querySelectorAll('[data-reconciliation-money]'));
  const targetLabel = document.querySelector('#reconciliationNumpadTarget');
  let activeInput = inputs[0] || null;

  function activate(input) {
    if (!input) return;
    activeInput = input;
    inputs.forEach((row) => row.classList.toggle('numpad-active', row === input));
    targetLabel.textContent = input.closest('label')?.firstChild?.textContent?.trim() || 'ยอดเงิน';
  }
  function setValue(value) {
    if (!activeInput) return;
    activeInput.value = value;
    activeInput.dispatchEvent(new Event('input', { bubbles: true }));
    activeInput.focus({ preventScroll: true });
  }
  function nextInput() {
    const index = inputs.indexOf(activeInput);
    activate(inputs[Math.min(inputs.length - 1, index + 1)] || inputs[0]);
    activeInput?.focus({ preventScroll: true });
  }

  inputs.forEach((input) => {
    input.addEventListener('focus', () => activate(input));
    input.addEventListener('pointerdown', () => activate(input));
  });
  document.querySelector('.reconciliation-numpad').addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button || !activeInput) return;
    const current = String(activeInput.value || '').replace(/\D/g, '');
    if (button.dataset.reconciliationKey !== undefined) {
      setValue(`${current}${button.dataset.reconciliationKey}`.replace(/^0+(?=\d)/, '').slice(0, 9));
    } else if (button.dataset.reconciliationAction === 'backspace') {
      setValue(current.slice(0, -1));
    } else if (button.dataset.reconciliationAction === 'clear') {
      setValue('');
    } else if (button.dataset.reconciliationAction === 'next') {
      nextInput();
    }
  });
  activate(activeInput);
})();
