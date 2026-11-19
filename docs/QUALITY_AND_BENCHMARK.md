# Qualitätskennzahlen und Messmethodik

## Qualitätskennzahl

```
Annahmequote je Import = (Gesamtzeilen - abgelehnte Zeilen) / Gesamtzeilen * 100
```

- Gleiche Produkt-ID in unterschiedlichen Importläufen: zählt erneut als gelesene und gegebenenfalls akzeptierte Zeile.
- Gleiche Produkt-ID mehrfach innerhalb einer Datei: zweite Zeile abgelehnt.
- Eine Quellzeile mit mehreren Prüfproblemen könnte mehrere `validation_issues` erzeugen. Daher ist **Anzahl Probleme** nicht gleich **Anzahl abgelehnter Zeilen**.
- Für `total_rows = 0` wird `null` ausgegeben, nicht automatisch 100 %.
- Für Datenqualität berücksichtigen wir nur abgeschlossene Importläufe (`completed`, `completed_with_issues`).
- Die Qualität wird pro Quell-Import bewertet, nicht als eindeutige Katalogkorrektheit oder Matching-Genauigkeit.

## Benchmark

Ausführung: `python benchmark.py --rows 1000 --repeats 3`.

1. Für jede Wiederholung eigene SQLite-In-Memory-DB erzeugen.
2. Reproduzierbare, deterministische Datensätze erzeugen.
3. Erstimport messen (Anzahl Neu muss N sein).
4. Gleiche Datensätze erneut importieren (Anzahl Unverändert muss N, Neu 0 sein).
5. Mediane über Wiederholungen ausgeben; Durchsatz mit N / Medianzeit berechnen.
6. Datenbank nach Messung verwerfen.

Keine Schreibvorgänge auf PostgreSQL oder Docker-Volumes. Achtung: Diese synthetische SQLite-Messung ist kein Vergleich mit einem echten Produktionsimport inkl. Dateiupload, API-Ausfällen, PostgreSQL und parallelen Nutzeranfragen.

## Nächste mögliche Verbesserungen

- PostgreSQL-Integrationstest mit separater *Test*-DB und temporären Daten.
- DB-optimierte Batch-UPSERTs statt einzelner Lookup-Queries pro Datensatz.
- P95/P99-Latenzen und Speicherverbrauch unter realistischen Datensätzen.
- Feldweise Profiling-Metriken (Nullrate, Wertebereiche, Kardinalität) mit expliziten Qualitätsregeln.
- Pagination für die gesammelten Importläufe (aktuell ist deren Übersicht auf 30 limitiert).
