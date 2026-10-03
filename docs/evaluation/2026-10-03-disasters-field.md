# Disasters field from S2iD (one row per municipal event, 1991–2025)

**Date:** 2026-10-03.

**Regime:** `pegasus-data fields --name disasters --root pegasus_data_home`.

**Source.** MIDR's CKAN dataset `s2id_sedec`, resource "1991 a 2025 - Danos
Informados" (86,323,744 bytes, cp1252, CC-BY).
- **Getting it.** MIDR's F5 firewall rejects any path ending in lowercase
  `.csv`, whatever the client: browser headers, cookies, even a browser
  navigation. The PDF beside it downloads. CKAN's bare
  `/resource/<id>/download` route serves the same file.

**Result:** 76,190 events, all dated.
- By group: climatological 37,260; hydrological 29,352; meteorological
  7,330; other 2,248.
- By status: 35,608 federally recognised, 40,582 registered.

**Checks against known disasters:**
- **Rio Grande do Sul, April–May 2024, hydrological:** 184 deaths reported
  across 463 municipalities (official toll about 183).
- **Petrópolis, 15 February 2022:** 235 deaths, 2,542 homeless, 9,225
  displaced (official toll 241).
