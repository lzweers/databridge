# DataBridge Demo – v0.4

1. Überblick: Bereits gespeicherte CSV- und API-Daten anzeigen.
2. API-Connector: Erklären, dass externe Daten auf eine gemeinsame Offer-Struktur normalisiert werden.
3. Importhistorie: Originaldaten, Prüfresultate und abweichende Werte vorführen.
4. **Automatisierung:** Mit deaktiviertem Zeitplan beginnen. Alle 5 Minuten einstellen, Aktivieren klicken.
5. **Jetzt ausführen** klicken. Im Worker erfolgt die eigentliche Verarbeitung unabhängig vom HTTP-Request.
6. Nach wenigen Sekunden zeigt das Monitoring den abgeschlossenen Versuch samt `import_id`.
7. Den verlinkten Import öffnen und die Originaldaten vorführen.
8. Den sofortigen Lauf wiederholen: Keine doppelten Angebote. Live-Ereignisse / History im Produktkatalog zeigen.
9. Erklären: Ein HTTP-Fehler wird im Ausführungsprotokoll gespeichert und mit begrenztem Retry eingeplant. Tests verwenden dafür einen simulierten API-Ausfall.
10. Pipeline wieder deaktivieren. Auf das separate `worker`-Service und die gespeicherten Zustände in PostgreSQL hinweisen.

> Nicht behaupten, das System sei bereits production-ready. Grenzen: kein Auth, nur ein fest konfigurierter Connector, begrenzte Crash-Recovery und kein Backfill verpasster Intervalle.
