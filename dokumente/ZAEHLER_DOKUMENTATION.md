# Zähler-Dokumentation

## Garten Strom

**Verbrauchsstelle:** Krummer Weg 40 m
**Versorger:** SWE Energie GmbH
**Aktueller Zähler:** 1DZG0061148558 (seit 25.09.2025)

### Zählerwechsel 25.09.2025

| | Zähler-Nr | Modell | Stand | Datum |
|---|-----------|--------|-------|-------|
| Alter Zähler | 36315107 | EMH Drehstromzähler ED300S | 2895 kWh (Endstand) | 25.09.2025 |
| Neuer Zähler | 1DZG0061148558 | DZG Zweirichtungszähler DWS7412.2V.G2 (Bj. 2023) | 0 kWh (Anfangsstand) | 25.09.2025 |

- Netzbetreiber: SWE Erfurt Netz
- Hinweis: Zweirichtungszähler, aber keine PV-Anlage vorhanden -- SWE-Standardverbau
- Quelle: SWE-Kundenportal + Foto-Dokumentation

### Zählerstände

| Datum | Stand (kWh) | Verbrauch (kWh) | Tage | kWh/d | Zähler | Quelle |
|-------|-------------|-----------------|------|-------|--------|--------|
| 06.06.2018 | 0 | - | - | - | 36315107 | Einbau, Rechnung SWE 2018 |
| 05.07.2018 | 41 | 41 | 29 | 1.41 | 36315107 | Rechnung SWE 2018 (Schätzung) |
| 06.07.2019 | 328 | 287 | 366 | 0.78 | 36315107 | Rechnung SWE 2019 (Kundenablesung) |
| 26.07.2020 | 748 | 420 | 386 | 1.09 | 36315107 | Rechnung SWE 2020 (Kundenablesung) |
| 02.07.2022 | 1080 | 332 | 706 | 0.47 | 36315107 | Rechnung SWE 2023, Periodenstart (Schätzung) |
| 27.06.2023 | 1304 | 224 | 360 | 0.62 | 36315107 | Rechnung SWE 2023 (Kundenablesung) |
| 02.08.2024 | 1873 | 569 | 402 | 1.42 | 36315107 | Rechnung SWE 2024 (Kundenablesung) |
| 12.07.2025 | 2817 | 944 | 344 | 2.74 | 36315107 | Rechnung SWE 2025 (Kundenablesung) |
| 25.09.2025 | 2895 | 78 | 75 | 1.04 | 36315107 | Zählerwechsel Endstand, SWE-Portal |
| 25.09.2025 | 0 | - | - | - | 1DZG0061148558 | Zählerwechsel Anfangsstand, SWE-Portal |
| 05.04.2026 | 208 | 208 | 192 | 1.08 | 1DZG0061148558 | Ablesung vor Ort, Foto |

### Preishistorie

| Gültig ab | Preis (brutto) | Tarif | Quelle |
|-----------|----------------|-------|--------|
| 01.09.2018 | 26,23 ct/kWh | Strom.mini | Rechnung 2019 |
| 01.01.2019 | 27,41 ct/kWh | Strom.mini | Rechnung 2019 |
| 01.01.2020 | 29,43 ct/kWh | Strom.mini | Rechnung 2020 |
| 01.07.2022 | 25,00 ct/kWh | Strom.mini SV | Rechnung 2023 |
| 01.10.2022 | 36,07 ct/kWh | Strom.mini SV | Rechnung 2023 |
| 01.01.2025 | 34,94 ct/kWh | Strom.fam SV | Rechnung 2025 |

---

### Session 2026-04-06

**Aktion:** Zählerwechsel Garten Strom dokumentiert + aktuelle Ablesung
**Daten:**
- Endstand alt: 2895 kWh (36315107, EMH ED300S), Datum 25.09.2025
- Anfangsstand neu: 0 kWh (1DZG0061148558, DZG DWS7412.2V.G2, Bj. 2023)
- Aktuelle Ablesung: 208 kWh am 05.04.2026
**Quelle:** SWE-Kundenportal + Foto-Ablesung vor Ort
**Dateien aktualisiert:** readings.json, config.json (meter_type/model ergänzt), index.html (meter_nr), ZAEHLER_DOKUMENTATION.md
**Plausibilität:**
- Endstand 2895 - Vorstand 2817 = 78 kWh in 75 Tagen = 1.04 kWh/d (im Rahmen)
- Neue Ablesung 208 kWh in 192 Tagen = 1.08 kWh/d (im historischen Rahmen 0.5-2.7 kWh/d)

### Session 2026-04-07

**Aktion:** Datenbereinigung aller Zähler
**Änderungen:**
- **fritz-gas readings.json:** source-Felder bei allen 11 Einträgen nachgetragen (Zählerwechsel, Rechnungen SWSZ 2024/2025, Eigenablesungen, App-Eingaben)
- **garten-strom config.json:** price_history aktualisiert — valid_from 2024-08-03 mit Netto-AP 29,36 ct, Grundpreis 120,60 EUR/a, Messtechnik 11,52 EUR/a (Rechnung SWE Strom-KRU 2025)
- **gustav-strom config.json:** Tarifinfos ergänzt (SWE Strom.natur maxi SV, VK 30819571, KNr 20293477, Sonderversorgung), price_history mit Netto-Detailfeldern ab 2024-08-17, alter Eintrag 2025-01-01 korrigiert auf 2024-08-17
- **garten-wasser config.json:** 2 price_history-Einträge ergänzt — Rechnung ThüWa 2025 (GP 120 EUR/a) + Preisanpassung ab 01.03.2025 (Bereitstellungspreis 123,96 EUR/a)
**Quelle:** Rechnungsdaten aus vorherigen Sessions, SWE-Kundenportal
**config.json fritz-gas:** keine Änderung nötig

### Session 2026-04-27 — Code-Abschluss

**Kontext:** Projekt wird ab sofort vollständig in Cowork weitergeführt. Claude Code wird für dieses Projekt nicht mehr verwendet.

**Code-Verbesserungen am SPA & E-Mail-System (committed):**
- Chart-Glättung mit gewichtetem 360-Tage gleitenden Durchschnitt (App + E-Mail-PNG)
- XSS-Schutz via `esc()`-Funktion für alle innerHTML mit dynamischen Daten
- `Promise.all` in `loadData()` (paralleles Laden config + readings)
- Viewport-Zoom freigegeben (WCAG-konform)
- `unescape(encodeURIComponent())` durch `TextEncoder` + `bytesToB64()` ersetzt
- `alert()` durch In-App `showError()` ersetzt
- matplotlib in GitHub Action auf `>=3.8,<4` gepinnt
- Offline-Erkennung F-06 verifiziert (war bereits implementiert)

**Datenpflege (committed):**
- Zählerwechsel Garten Strom: 36315107 → 1DZG0061148558 (25.09.2025), Endstand 2895 kWh, Anfangsstand 0 kWh
- Aktuelle Ablesung Garten Strom: 208 kWh (05.04.2026), Quelle Foto vor Ort
- UTF-8-Encoding-Fix in garten-wasser/readings.json (`SchÃ¤tzung` → `Schätzung`)
- Datenbereinigung: source-Felder fritz-gas, price_history-Erweiterungen (Netto-AP, Grundpreis, Messtechnik) für garten-strom, gustav-strom, garten-wasser

**Finaler Merge (committed):**
- garten-strom + gustav-strom config.json: Adressen, Tarif-Details, Vertragskonten, aktuelle Preise vom 07.04.2026 aus SWE-Portal **mit** Zählerwechsel-Doku zusammengeführt
- previous_meters-Array bleibt erhalten neben address/tarif/kundennummer/vertragskonto

**Sync-Status:**
- gas-tracker-clone/ → Referenz, alles auf origin/main
- gas-tracker/ → mit gemergten configs synchronisiert
- gas-tracker-v2/ → kein meters/-Ordner, wird in Cowork neu strukturiert

**Offen:** Keine Code-spezifischen Aufgaben mehr. Fortsetzung in Cowork.
