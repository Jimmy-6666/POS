(() => {
  document.querySelectorAll('.print-barcode').forEach(svg => {
    const value = svg.dataset.value;
    try {
      JsBarcode(svg, value, {
        format: 'CODE128',
        width: 1.45,
        height: 42,
        margin: 3,
        displayValue: true,
        fontSize: 13,
        textMargin: 2,
        background: '#ffffff',
        lineColor: '#000000'
      });
    } catch (_) {
      const cell = svg.closest('.barcode-cell');
      if (cell) cell.textContent = value;
    }
  });
})();
