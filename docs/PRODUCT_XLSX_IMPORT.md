# Product XLSX import and export

Only an authenticated `admin` can use the XLSX controls on **สินค้าทั้งหมด**.
The server also checks the role, so managers and cashiers cannot call the
export, preview, or confirm endpoints directly.

## Export and template

Use **ส่งออก XLSX** to download the current catalogue. It is the supported
template and contains a `Products` sheet, frozen header, text-formatted SKU and
barcode columns, active category/unit/status validation, and an `Instructions`
sheet. A blank example artifact from the same stable headers is generated at
`outputs/sprint-4-product-xlsx/product-import-template.xlsx` for this hand-off;
the live export must be preferred because its dropdowns use the store's active
categories and units.

## Identity and import rules

- `product_uuid` is the only identity key. Keep an exported UUID to update that
  product. A blank UUID creates a product with a system-generated UUID. An
  unknown, invalid, or repeated UUID is rejected.
- Barcode and SKU remain editable unique business fields. They never match a
  product during import, so changing either does not change identity.
- New rows require barcode, Thai name, category, unit, cost price, and selling
  price. Optional blank cells leave existing values unchanged. Use `__CLEAR__`
  only to clear SKU, English name, or online maximum quantity.
- Enter no spreadsheet formulas or values beginning with `=`, `+`, `-`, or `@`.
  Those values are rejected to protect later workbook users.
- Existing stock is reference-only in the workbook; use normal receiving or
  stock adjustment to change it. A new row's stock value is saved as an audited
  `opening_balance` stock movement.

Uploading only parses and previews the file. Confirmation is required, is
one-time, and commits the complete import in one SQLite transaction. A preview
expires after 15 minutes and is not persisted. Audit records retain the admin,
filename, time, and batch counts; each created or updated product has a
separate audit entry containing only changed field names, never spreadsheet
content. The system revalidates product UUIDs, active references, and SKU/
barcode uniqueness after it obtains the write lock, then rolls back the whole
batch if anything changed after preview.
