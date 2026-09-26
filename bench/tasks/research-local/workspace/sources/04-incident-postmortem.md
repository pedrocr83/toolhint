# Postmortem: RouteLoom outage at Tilburg, 9 April 2026

**Severity:** high. **Duration:** 7 hours (06:10 to 13:10).

## What happened
At 06:10 the RouteLoom connector in our data centre stopped syncing with the cloud service. Pickers received no routes, and the shift lead switched the site to manual picking from printed lists at 06:40. RouteLoom routing was restored at 13:10.

## Impact
- 1,900 order lines were shipped late (after the 14:00 carrier cut-off).
- The pick rate on manual lists was about 20% below the pre-pilot baseline for the rest of the day.

## Root cause
The API certificate used by the connector had expired. RouteLoom had issued the certificate with a one-year lifetime during a 2025 proof of concept, and nobody on either side monitored its expiry.

## Actions
1. **RouteLoom:** automatic certificate renewal plus expiry alerts, shipped 16 April 2026. Done.
2. **RouteLoom:** SLA service credit of €4,500. Received.
3. **Us:** add certificate expiry checks for all vendor connectors to our network operations monitoring. Open, owner IT, due before any rollout.
4. **Us:** a documented manual-picking fallback for every site before go-live. Open, owner Operations.
