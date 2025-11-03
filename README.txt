hoerbuch – Text-to-Speech Hörbuch-Generator mit Piper TTS
==========================================================

Beschreibung
------------
Dieses kleine CLI-Tool wandelt Textdokumente (.txt, .docx, .odt) in komprimierte OGG-Audiodateien um, 
unter Verwendung von Piper TTS. 
Dank Streaming-Mode können auch große Dokumente (z.B. ganze Bücher) effizient in Audio konvertiert werden, 
ohne den Arbeitsspeicher zu überlasten. 
Die Ausgaben lassen sich direkt mit einem Player wie mpv anhören, während sie erzeugt werden.

Features
--------
- Unterstützt Textdateien (.txt), Word (.docx) und OpenDocument (.odt)
- Streaming-Ausgabe direkt als OGG (Vorbis)
- Live-Abspielbar während der Generierung
- Absätze werden automatisch gesplittet → natürliche Pausen
- Locale-fähige Fehlermeldungen (z.B. Deutsch / Englisch)
- Flexible Wahl der ONNX-Stimme, Standard: de_DE-thorsten-high.onnx

Installation
------------
1. Piper TTS installieren:
   python3 -m pip install piper-tts

2. Abhängigkeiten für Textformate:
   sudo apt install python3-docx python3-odf python3-soundfile

3. Stimme herunterladen (z.B. de_DE-thorsten-high.onnx) und in 
   hoerbuch/models/ ablegen oder unter /opt/models/

4. Lokalisierung vorbereiten (optional):
   - locales/de/LC_MESSAGES/messages.po → kompilieren:
     msgfmt locales/de/LC_MESSAGES/messages.po -o locales/de/LC_MESSAGES/messages.mo

Benutzung
----------
Basic:
    ./hoerbuch.py <input_file>

Beispiele:
1. Textdatei in OGG konvertieren:
    ./hoerbuch.py README.txt

2. Word-Dokument mit Leerzeichen im Namen:
    ./hoerbuch.py "100 Kieselsteinchen (Band 1).docx"

3. Mit alternativem ONNX-Stimmfile:
    ./hoerbuch.py "100 Kieselsteinchen.docx" --voice models/de_DE-thorsten-high.onnx

Ausgabe:
- Standardmäßig wird eine OGG-Datei im gleichen Ordner erzeugt, mit gleichem Namen:
  z.B. hoerbuch.txt → hoerbuch.ogg
- Die Datei kann direkt mit mpv oder anderen Playern abgespielt werden:
    mpv "100 Kieselsteinchen (Band 1).ogg"

Tipps
-----
- Für sehr große Dokumente (~70.000 Wörter) empfiehlt es sich, die Ausgabe direkt zu streamen und live zu kontrollieren.
- Mehrere aufeinanderfolgende Leerzeilen werden automatisch auf maximal zwei zusammengefasst, um übermäßige Pausen zu vermeiden.
- Fehlermeldungen passen sich an die Systemsprache an (lokalisierbar via gettext).

Lizenz
-------
Füge hier die passende Lizenz ein, z.B. MIT, GPL, Apache 2.0, je nach Wunsch.

---

Viel Spaß beim Erstellen von Hörbüchern! 🎧

