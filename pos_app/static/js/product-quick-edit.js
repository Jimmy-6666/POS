(() => {
  const scanForm = document.querySelector('[data-quick-scan-form]');
  const scanInput = document.querySelector('#quickProductBarcode');
  const editForm = document.querySelector('[data-quick-product-form]');
  const saveButton = document.querySelector('#quickProductSave');
  const notFoundDialog = document.querySelector('#quickProductNotFound');
  const editorDialog = document.querySelector('[data-quick-product-dialog]');
  const mobileEditorViewport = window.matchMedia('(max-width: 600px)');

  const editorIsModal = () => {
    try {
      return editorDialog?.matches(':modal') || false;
    } catch (_error) {
      return false;
    }
  };

  const syncEditorDialog = () => {
    if (!editorDialog) return;

    if (mobileEditorViewport.matches) {
      document.body.classList.add('quick-product-modal-open');
      if (typeof editorDialog.showModal === 'function' && !editorIsModal()) {
        editorDialog.removeAttribute('open');
        editorDialog.showModal();
      } else if (!editorDialog.open) {
        editorDialog.setAttribute('open', '');
      }
      return;
    }

    document.body.classList.remove('quick-product-modal-open');
    if (editorIsModal()) editorDialog.close();
    editorDialog.setAttribute('open', '');
  };

  if (scanForm && scanInput) {
    scanForm.addEventListener('submit', (event) => {
      scanInput.value = scanInput.value.trim();
      if (!scanInput.value) {
        event.preventDefault();
        scanInput.focus();
      }
    });
  }

  if (editForm && saveButton) {
    editForm.addEventListener('submit', () => {
      saveButton.disabled = true;
      saveButton.textContent = 'กำลังบันทึก...';
    });
  }

  if (notFoundDialog && typeof notFoundDialog.showModal === 'function') {
    notFoundDialog.removeAttribute('open');
    notFoundDialog.showModal();
  }

  if (editorDialog) {
    syncEditorDialog();
    editorDialog.addEventListener('close', () => {
      document.body.classList.remove('quick-product-modal-open');
      scanInput?.focus();
    });
    if (typeof mobileEditorViewport.addEventListener === 'function') {
      mobileEditorViewport.addEventListener('change', syncEditorDialog);
    } else {
      mobileEditorViewport.addListener(syncEditorDialog);
    }
  }
})();
