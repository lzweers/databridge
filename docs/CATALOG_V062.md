# DataBridge v0.6.2 – Product Details & Filtered CSV Export

## Zweck

Der Produktkatalog bleibt serverseitig durchsuchbar und filterbar. Die neue Seitenansicht führt zwei Funktionen hinzu:

1. **Produktdetails:** Ein Seitenpanel zeigt aktuelle Angebotseigenschaften, Quell-ID, letzte Änderung und das jüngste dokumentierte Lineage-Ereignis. Über „Vollständigen Verlauf öffnen“ gelangt man weiterhin zur bestehenden Historienansicht. Ältere Importe ohne v0.3-Historie werden ausdrücklich gekennzeichnet.
2. **CSV-Export:** Alle Treffer der aktuellen Suche/des Quellenfilters und in der gewählten Sortierung herunterladen, **nicht nur die aktuelle 20er-Seite**. Der Export ist auf 10.000 Treffer begrenzt und weist bei Überschreitung auf Filterung hin. Währungen werden unverändert ausgewiesen, unbekannte Währungen (`XXX`) als „Unbekannt“.

## Architektur

- API `GET /api/catalog/offers`: serverseitige Suche, Pagination und Sortierung (bestehend).
- API `GET /api/catalog/export.csv`: gleicher SQL-Filter und dieselbe Sortierung, ohne Pagination. CSV wird als UTF-8 mit BOM, Semikolon als Trennzeichen und klarer Währungsspalte ausgeliefert.
- Bestehende API `GET /api/offers/{id}/lineage`: Datenquelle für das Produktdetail-Panel; keine zweite Historienlogik.
- Unvertraute Textwerte werden vor CSV-Formelausführung geschützt (`=`, `+`, `-`, `@`, auch mit führenden Leerzeichen).
- Es gibt **keine** Datenbankmigration, keine neuen Tabellen und keinen Datenbank-Reset.

## Update für lokale Windows-Installation

Im Projektordner `databridge-starter` in PowerShell:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\databridge-v062-update.zip" -DestinationPath "." -Force
docker compose up -d --build backend frontend
```

Dann `http://localhost:5173` öffnen und `Strg + F5` drücken. Automatisierung/Worker bleiben unverändert.

## Testen

1. Im Produktkatalog einen Suchbegriff eingeben, z. B. `USB`. Ein Produkt über **Details** öffnen; **Schließen**, Escape und Klick außerhalb schließen das Panel. Vollständigen Verlauf öffnen.
2. Quelle auswählen und den Katalog sortieren. **CSV exportieren** klicken. Der Export muss alle gefilterten Datensätze enthalten, auch die zweite Katalogseite.
3. CSV mit Excel oder Texteditor öffnen. Demo-Preise ohne Währung dürfen nicht als Euro erscheinen.
4. Backend-Tests isoliert von der normalen DB starten (setzt die Testdatenbank auf SQLite):

```powershell
docker compose run --rm -e DATABASE_URL=sqlite:///./databridge-test.db backend python -m pytest -q
```

Erwartet **30 passed** bei v0.6.2 ohne weitere Änderungen.

5. Frontend-Produktionsbuild:

```powershell
docker compose run --rm frontend npm run build
```

## Verifikation

- Backend: `30 passed` mit SQLite-Testumgebung.
- TSX: Syntaxprüfung erfolgreich.
- Der vollständige npm/TypeScript/Vite-Build konnte im Erstellungscontainer nicht durchgeführt werden, da die npm-Registry nicht erreichbar war. Deshalb auf dem Windows-PC ausführen.

## Sicherheit / Veröffentlichung

Die lokale Demo besitzt weiterhin **keine Benutzer-Authentifizierung**. API und Export nicht ohne Authentifizierung, Rate-Limits und weitere Sicherheitsprüfung öffentlich erreichbar machen.
