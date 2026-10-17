# Bewertungsanleitung (etwa 30 Minuten)

Du bewertest 96 automatische Übersetzungen von Schweizerdeutsch ins Hochdeutsche.
Zwei Personen bewerten dieselben Zeilen unabhängig voneinander. **Sprich dich nicht ab.**

## Pro Zeile siehst du

- `swiss_german`: den Satz im Dialekt (das, was das Modell bekommen hat)
- `reference_de`: eine korrekte hochdeutsche Übersetzung
- `output`: die Übersetzung des Modells

Trag in `adequacy` eine Zahl von **1 bis 5** ein. `comment` ist freiwillig.

## Die Frage

**Sagt der `output` dasselbe wie der Dialektsatz?**

Bewerte die **Bedeutung**, nicht die Wortwahl. Eine andere, aber richtige Formulierung
ist kein Fehler. Kleine Grammatik- oder Rechtschreibfehler sind egal, solange die Bedeutung stimmt.

| Note | Bedeutung |
|---|---|
| **5** | Alles stimmt. Gleiche Bedeutung, nichts fehlt, nichts dazuerfunden. |
| **4** | Fast alles stimmt. Ein kleines Detail fehlt oder ist leicht anders. |
| **3** | Die Hauptaussage stimmt, aber ein wichtiger Teil ist falsch oder fehlt. |
| **2** | Nur einzelne Teile stimmen. Die Hauptaussage ist falsch. |
| **1** | Nichts stimmt, oder der Output ist kein Satz (Erklärung, Dialekt kopiert, Unsinn). |

## Beispiele

| Dialekt | Output | Note |
|---|---|---|
| Im glichu Jahr isch d'erscht Clubhitta am Tödi entstandu. | Im gleichen Jahr entstand die erste Clubhütte am Tödi. | 5 |
| Sie het as Lächla erzwunga und het Müah kah, ruhig z schnuufa. | Sie zwang sich zu einem Lächeln und konnte kaum ruhig atmen. | 5 |
| Sie het as Lächla erzwunga und het Müah kah, ruhig z schnuufa. | Sie hat ein Lächeln erzwungen und blieb ruhig. | 3 |
| Sie het as Lächla erzwunga und het Müah kah, ruhig z schnuufa. | Sie hat als Lächeln erzwungen und hat mich dazu gebracht, ruhig zu bleiben. | 2 |

Die Referenz hilft dir, wenn du ein Dialektwort nicht kennst. Sie ist aber manchmal frei
übersetzt oder hat Tippfehler. Entscheidend ist der Dialektsatz.

## Danach

Speichere die Datei als `bewertung_<deine-initialen>.csv` und schick sie an Erik.
Ändere keine anderen Spalten und keine Reihenfolge.
