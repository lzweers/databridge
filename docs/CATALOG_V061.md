# DataBridge v0.6.1 — Serverseitiger Produktkatalog

## Installation (bestehende v0.6-Installation)

1. Backend/Frontend-Quellcode sichern oder committen.
2. Das Update-ZIP im Projektverzeichnis `databridge-starter` entpacken, dabei die Quelldateien überschreiben:
   ```powershell
   Expand-Archive -Path "$env:USERPROFILE\Downloads\databridge-v061-catalog-update.zip" -DestinationPath "." -Force
   ```
3. Container mit den veränderten Dateien neu bauen:
   ```powershell
   docker compose up -d --build backend frontend
   ```
4. Browser auf `http://localhost:5173` öffnen, ggf. `Strg + F5`.
5. Im Produktkatalog nach `USB`, `A-1001` oder einer DummyJSON-ID suchen. Quellenfilter und Sortierung probieren. Bei 28 gespeicherten Angeboten zeigt die Standardansicht zwei Seiten (20 + 8).

**Wichtig:** Dieses Update enthält ausschließlich Backend-API-Code, React/CSS und Tests/Dokumentation. **Keine Datenbankmigration**, kein `drop_all`, kein `docker compose down -v`. Vorhandene PostgreSQL-Daten werden durch das Einspielen nicht bewusst verändert.

## Umfang

- `GET /api/catalog/offers?search=usb&source=Lieferant%20A&sort=name_asc&limit=20&offset=0`
- Suche nach Produktname oder externer ID (Groß-/Kleinschreibung wird bei ASCII ignoriert)
- Lieferantenfilter, Sortierung nach Name, Bestand, Quelle oder Neuheit
- Stabile serverseitige Seitennavigation mit `total`, `offset`, `limit` und Quellenliste
- `sort` ist auf eine feste Auswahlliste beschränkt; `limit` maximal 100; `%` und `_` werden als normale Suchzeichen behandelt
- React: 280-ms-Sucheingabe-Verzögerung, Abbruch veralteter Anfragen, Lade-, Fehler- und Leerzustände
- Legacy-Endpunkt `/api/offers` bleibt unverändert; kein Breaking Change für bestehende Aufrufer

## Tests (sicher isoliert)

`docker compose run --rm backend python -m pytest -q`

Vier neue Integrationsfälle verwenden eine eigens angelegte **SQLite-In-Memory-Datenbank**. Bereits vorhandene Tests müssen ebenfalls in der abgesicherten SQLite-Testumgebung laufen. Keine Tests gegen eine PostgreSQL-Datenbank ausführen.

`docker compose run --rm frontend npm run build`

## Grenzen der Version

- Suchvorgänge sind für einen kleinen Katalog ausgelegt; für Millionen Datensätze wären zusätzliche Indizes (z. B. PostgreSQL trigram) und Messungen sinnvoll.
- Preissortierung ist absichtlich nicht enthalten, weil einige Demo-API-Preise keine belegte Währung besitzen.
- Paginierung nutzt `offset` (ausreichend für diese Demogröße); bei stark veränderlichen, großen Datenbeständen wäre Cursor-Pagination robuster.
- Die neue Oberfläche hat einen geprüften TypeScript-/JSX-Syntaxdurchlauf. Ein vollständiger Frontend-Build war in der Erstellungssandbox ohne npm-Abhängigkeiten nicht möglich und muss lokal bestätigt werden.
