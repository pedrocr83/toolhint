# RouteLoom pilot: Tilburg DC, final report

**Period:** 2 March to 8 May 2026 (10 weeks)
**Site:** Tilburg distribution centre, 48 order pickers across two shifts
**Prepared by:** Operations Excellence, 15 May 2026

## What we tested
RouteLoom replaces the fixed pick paths in our WMS (v8) with routes recalculated for every pick wave. It runs as a cloud service and syncs with the WMS every 90 seconds through a connector installed in our data centre.

## Results
| Measure | Baseline (Q4 2025) | Pilot, weeks 7 to 10 |
|---|---|---|
| Pick rate (order lines per picker-hour) | 112 | 131 |
| Mis-pick rate | 1.9% | 1.1% |
| Average walking distance per line | 38 m | 29 m |

The pick rate improvement is 17%, measured over the last four weeks once pickers were used to the new routes. The first weeks were lower while people adapted (see `02-pilot-metrics.csv`).

## Cost of the change
- Training took 6 hours per picker, 288 hours in total.
- One major outage on 9 April stopped RouteLoom for most of a shift; see `04-incident-postmortem.md`.

## Picker feedback
71% of pickers who answered the end-of-pilot survey (41 of 48 answered) prefer the new routes. The main complaint was that routes change without warning when a rush order lands mid-wave.

## Finance estimate
Finance extrapolated the pilot's labour savings to all six sites (Tilburg, Rotterdam, Liège, Antwerp, Venlo and Duisburg) at **€312,000 per year**, assuming the same 17% gain and current wage rates. This is an estimate: the other five sites have different layouts, and Duisburg runs a partly automated zone that routing does not affect.
