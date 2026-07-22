# Eval Dataset Labelling Guide

`eval_dataset.csv` is a **static benchmark file** used to evaluate the accuracy of the Ledger Agent classification system. It must never be modified by the live app.

---

## Column Reference

| Column | Type | Description |
|--------|------|-------------|
| `description` | string | The raw transaction description as it appears from Plaid (e.g., "WHOLE FOODS MKT #123"). Use realistic-looking but fictitious values. |
| `amount` | decimal | Positive number, no currency symbol, no thousands separator (e.g., `42.50`, `1200.00`). |
| `date` | string | ISO 8601 date string: `YYYY-MM-DD` (e.g., `2026-05-12`). |
| `correct_category` | string | The single correct category for this transaction. Must exactly match one of the 10 valid values (case-sensitive) — see list below. |
| `is_genuinely_ambiguous` | boolean | `true` or `false` (lowercase). See the ambiguity rule below. |
| `notes` | string | Optional freeform explanation of your labelling decision. Leave blank if nothing to add (do not write `""`). |

---

## The Ambiguity Rule

Set `is_genuinely_ambiguous=true` when **a reasonable human would be uncertain which category is correct** even after reading both the description and amount. The key test: would two different reasonable people, given only this row's data, disagree on the category?

**Ambiguous examples (`is_genuinely_ambiguous=true`):**
- `Amazon, 49.99` — could be Shopping, Entertainment (Prime subscription), or Groceries (Amazon Fresh)
- `Costco, 134.72` — could be Groceries (bulk food) or Shopping (household goods, clothing)
- `CVS Pharmacy, 23.40` — could be Healthcare (medication) or Shopping (cosmetics, cleaning supplies)
- `Target, 67.80` — could be Shopping or Groceries depending on what was bought

**Unambiguous examples (`is_genuinely_ambiguous=false`):**
- `Netflix, 15.99` → Entertainment (streaming subscription, obviously)
- `Uber, 22.50` → Transportation (ride-share, obviously)
- `Whole Foods Market, 87.34` → Groceries (grocery store, obviously)
- `Rent payment, 2100.00` → Housing (obvious from description)
- `PG&E, 95.00` → Utilities (utility company)

**When in doubt, lean toward `false`.** Only mark `true` if you genuinely cannot decide which category is more correct.

---

## Valid `correct_category` Values

These are the 10 seeded default categories. Values are **case-sensitive** — copy exactly as shown:

```
Groceries
Dining
Transportation
Utilities
Housing
Healthcare
Entertainment
Shopping
Transfer
Uncategorized
```

Do not use variations like `Food`, `Groceries & Dining`, `grocery`, or `transport`. If a transaction truly doesn't fit any category, use `Uncategorized`.

---

## CSV Format Rules

- No quotes around field values unless the description contains a comma
- `is_genuinely_ambiguous`: always lowercase `true` or `false`
- `amount`: positive decimal, no `$`, no commas (e.g., `4.99`, `1234.56`)
- `date`: `YYYY-MM-DD` only
- `notes`: leave blank (not `""`) when you have nothing to add

---

## Important: This File is a Static Benchmark

- `eval_dataset.csv` is **read-only at runtime** — the live app never writes to it
- It is the ground-truth reference for eval runs (Story 4.2)
- All rows must use **fictitious transaction data** — never use real account data
- Add rows across the full range of categories for a representative benchmark (aim for 100–150 rows in Story 4.1)
