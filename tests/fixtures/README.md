# Synthetic fixtures

These images were generated specifically for testing this package. They do not contain customer
data, private receipts, screenshots from commercial applications, or downloaded internet content.

| Fixture                | Expected payable total | Purpose                                           |
| ---------------------- | ---------------------: | ------------------------------------------------- |
| `clean-screenshot.png` |            INR 1280.50 | Clean amount-due label                            |
| `multiple-totals.png`  |             INR 604.50 | Subtotal, tax, fee, and grand-total competition   |
| `angled-photo.jpg`     |              USD 85.47 | Rotation, compression, and generic total fallback |
| `wallet-after-total.png` |          INR 800.00 | Amount paid after wallet deduction outranks grand total |
| `cash-and-change.png` |               INR 85.47 | Generic total must not become cash tendered or change |
| `zero-payable.png` |                   INR 0.00 | Full coupon coverage is a zero suggestion, not missing evidence |
| `rupee-marker.png` |                 INR 638.00 | Rupee symbol adjacent to the amount |
| `savings-only.png` |                      None | Savings and discounts alone must not become a payable amount |
| `no-payable-label.png` |                  None | Order number and delivery estimate without a payable label |

The USD angled-photo fixture is historical and is not exercised by the current INR-only
recognition integration tests. It does not establish support for printed receipt photos.

The six capability fixtures added in September 2026 were rendered locally with Pillow onto
960 × 650 white canvases. They contain the heading `SYNTHETIC RECEIPT - TEST DATA` at (50, 35)
and the rows below starting at (50, 140), spaced 65 px apart. Text is 32 px Arial, except
`rupee-marker.png`, which uses SFNS to render the actual ₹ glyph. Fonts are rasterized into
the fixtures; running tests does not require these fonts.

- `wallet-after-total.png`: Item total: INR 1000.00; Grand total: INR 1000.00;
  Wallet: INR 200.00; Amount paid: INR 800.00.
- `cash-and-change.png`: TOTAL: INR 85.47; Cash: INR 100.00; Change: INR 14.53.
- `zero-payable.png`: Subtotal: INR 500.00; Coupon: INR 500.00; Amount due: INR 0.00.
- `rupee-marker.png`: Amount paid: ₹638.00.
- `savings-only.png`: Total savings: INR 240.00; Discount: INR 20.00.
- `no-payable-label.png`: Order number 983751; Delivery in 20 minutes;
  Thank you for shopping.

Real receipt failures must be reduced to a synthetic reproduction before being contributed.
