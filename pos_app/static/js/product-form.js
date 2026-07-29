(() => {
  function setupProductImagePreview() {
    const browse = document.querySelector('#productImageBrowse');
    const camera = document.querySelector('#productImageCamera');
    const preview = document.querySelector('#productImagePreview');
    const remove = document.querySelector('#removeProductImage');
    const currentImage = document.querySelector('#currentProductImage');
    if (!browse || !preview) return;

    const image = preview.querySelector('img');
    let previewUrl = '';
    function clearPreview() {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = '';
      image.removeAttribute('src');
      preview.hidden = true;
      if (currentImage) currentImage.hidden = false;
    }
    function choose(input, otherInput) {
      const file = input.files && input.files[0];
      if (!file) return; // Camera cancellation and denied access leave the current selection intact.
      if (otherInput) otherInput.value = '';
      clearPreview();
      if (currentImage) currentImage.hidden = true;
      previewUrl = URL.createObjectURL(file);
      image.src = previewUrl;
      preview.hidden = false;
    }
    browse.addEventListener('change', () => choose(browse, camera));
    if (camera) camera.addEventListener('change', () => choose(camera, browse));
    if (remove) remove.addEventListener('click', () => {
      browse.value = '';
      if (camera) camera.value = '';
      clearPreview();
    });
    window.addEventListener('pagehide', clearPreview, {once: true});
  }

  setupProductImagePreview();

  const cost = document.querySelector('[name=cost]');
  const price = document.querySelector('[name=price]');
  const profitAmount = document.querySelector('#profitAmount');
  const profitPercent = document.querySelector('#profitPercent');
  if (!cost || !price || !profitAmount || !profitPercent) return;

  function updateProfit() {
    const costValue = Number(cost.value) || 0;
    const priceValue = Number(price.value) || 0;
    const profit = priceValue - costValue;
    profitAmount.value = `${profit.toFixed(2)} บาท`;
    profitPercent.value = costValue > 0 ? `${(profit / costValue * 100).toFixed(2)}%` : '—';
  }
  cost.addEventListener('input', updateProfit);
  price.addEventListener('input', updateProfit);
  updateProfit();
})();
