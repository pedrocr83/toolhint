# Warehouse routing software: recommendation

**Recommendation:** sign with RouteLoom for all six sites by 15 July 2026 (05-steering-minutes.md), subject to two conditions: certificate monitoring in place before rollout, and the works council consultations at Rotterdam and Liège started now.

## Why RouteLoom
- **Measured, not promised:** the Tilburg pilot raised the pick rate from 112 to 131 lines per picker-hour (+17%) and cut mis-picks from 1.9% to 1.1% (01-pilot-report.md, 02-pilot-metrics.csv). Pathwise has no pilot with us, only single-site vendor references (03-vendor-quotes.md).
- **Meets the timing criterion:** signed by 15 July, all sites are live by mid-October, before peak season starts on 2 November (03-vendor-quotes.md, 05-steering-minutes.md). Pathwise needs WMS v9, which the WMS vendor cannot deliver before Q1 2027, so it would miss peak 2026 (05-steering-minutes.md).
- **Meets the payback criterion:** €214,000 a year plus €38,000 one-time against an estimated €312,000 a year in labour savings is roughly €98,000 net a year, so payback in about 5 months, well inside the CFO's 18-month limit (01, 03, 05).

## Key numbers
| | RouteLoom | Pathwise |
|---|---|---|
| Subscription per year | €214,000 | €176,000 |
| One-time integration | €38,000 | €95,000 |
| 3-year cost | €680,000 | €623,000 |
| Live before peak 2026 | Yes | No (WMS v9 in Q1 2027) |
| Evidence in our warehouses | Pilot | None |

Pathwise is €57,000 cheaper over three years (03-vendor-quotes.md), but starting at least five months later forgoes more than that in savings at the estimated rate.

## Risks
- **Outage risk:** the 9 April outage stopped routing for 7 hours and delayed 1,900 order lines; the root cause was an expired API certificate (04-incident-postmortem.md). The vendor now auto-renews certificates, but our own expiry monitoring and a manual-picking fallback per site are still open actions.
- **The benefit is an estimate:** the €312,000 extrapolates Tilburg's 17% to five sites with different layouts, and Duisburg's automated zone will not benefit (01-pilot-report.md).
- **Lock-in:** 3-year minimum term; Legal is checking for an exit clause (05-steering-minutes.md).
- **Change management:** 6 hours of training per picker, and pickers dislike routes changing mid-wave (01-pilot-report.md).

## Open questions
1. Can the contract include an exit clause if other sites miss the target? (05)
2. Will the works council consultations at Rotterdam and Liège (6 to 8 weeks) finish in time for the second wave? (05)
3. What gain should we expect at Duisburg given its automation? (01)

## What doesn't add up
- The Sales Director's email says the pilot showed "25% faster picking" (06-email-sales-director.txt). The pilot measured 17% (01-pilot-report.md); no week in the metrics shows 25% (02-pilot-metrics.csv).
- The same email calls Pathwise the obvious choice at €38,000 a year cheaper. The annual figure is right, but it ignores Pathwise's €95,000 integration, the missing evidence, and that it cannot be live before peak season.
- Pathwise's better SLA (99.9% against 99.5%) is real, but the email does not weigh it against the timing criterion (03, 06).
