# Care Card — Hospital & Pharmacy Subscription Card Program

A complete, installable Frappe application implementing an annual subscription
(loyalty) card for a hospital and its affiliated pharmacies.

* **App name:** `care_card`
* **Publisher:** Kreatao
* **Compatibility:** Frappe **v15 / v16**. ERPNext optional — the app installs
  and runs on a bare Frappe bench, and lights up billing integration
  automatically when `Sales Invoice` / `POS Invoice` are present.
* **HIS integration:** ERPNext Healthcare *or* a third-party HIS such as
  **KareXpert** through the signed inbound API adapter.
* **Market:** Oman / GCC — OMR, 5% VAT, Fri–Sat weekend, EN/AR, PDPL-aware.
* **License:** MIT

---

## Install

```bash
cd ~/frappe-bench
bench get-app care_card /path/to/care_card
bench --site yoursite.local install-app care_card
bench --site yoursite.local migrate
bench build --app care_card
```

After install the app seeds a ready-to-run program:

* Program **Care Card Program** — 12 month validity, 30/15/7/1 day reminders
* Tiers **Gold** (25 OMR) and **Platinum** (40 OMR)
* Six benefit categories with the full discount matrix
* OTC discount bands (5–35% Gold / 15–45% Platinum)
* WhatsApp message templates (EN + AR)
* Seven roles with permissions

## The discount matrix (seeded)

| Benefit category | Gold | Platinum |
|---|---|---|
| Consultation | 20% | 30% |
| Lab Investigation | 25% | 35% |
| Radiology Investigation | 20% | 30% |
| Inpatient Treatment | 15% | 25% |
| Prescription Medication | 5% | 15% |
| OTC Medication | 5–35% (rule driven) | 15–45% (rule driven) |

## Core objects

| DocType | Role |
|---|---|
| `Care Card` | The membership. Stable card number for life; one `Care Card Term` row per paid year. |
| `Care Card Ledger Entry` | Immutable money ledger — Fee Collected / Discount Given / Copay Shared / Reversal. Everything analytical reads from here. |
| `Care Card Usage` | Submittable redemption document, one per discounted bill. |
| `Care Card Discount Rule` | Override layer producing the OTC bands. Item > Brand > Item Group > Category default. |
| `Care Card Insurance Rule` | Copay sharing — a 10% copay becomes 5% patient / 5% hospital. |

## Portals

| Route | Audience |
|---|---|
| `/care-card` | Public — compare tiers, register, pay, receive the digital card |
| `/my-card` | Member — card + QR, dependents, visits, savings vs fee, renew |
| `/card-desk` | Counter & pharmacy staff — sell, verify, record usage, resend, renew |

## External API (HMAC signed)

| Method | Purpose |
|---|---|
| `care_card.api.external.verify` | card number / QR → status, tier, beneficiaries, remaining caps |
| `care_card.api.external.quote` | basket in → priced basket + per-line explanation (no ledger write) |
| `care_card.api.external.commit` | finalised bill in → usage + ledger entries (idempotent) |
| `care_card.api.external.reverse` | reverse a committed bill |

Signature: `HMAC-SHA256(secret, f"{timestamp}.{raw_body}")` in the
`X-CareCard-Signature` header, with `X-CareCard-Timestamp` inside a 300s window.

## Reports

Card Register · Member Utilization & Breakeven · Discount by Benefit Category ·
Visit & Dependent Usage Log · Program P&L · Renewal Pipeline ·
Insurance Copay Sharing · Channel & Agent Performance

## Economic costing

Each `Care Benefit Category` carries a **margin factor** — the share of a granted
discount that is a real margin cost. Pharmacy OTC ≈ 100%, consultation ≈ 30%
(largely unused capacity). Reports show both patient-facing savings and the true
economic cost, so breakeven analysis does not overstate the program's cost.
