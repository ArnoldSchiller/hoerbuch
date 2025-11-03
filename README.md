# hoerbuch
hoerbuch – Text-to-Speech Hörbuch-Generator mit Piper TTS

## Beschreibung
------------
Dieses CLI-Tool wandelt Textdokumente (.txt, .docx, .odt, .epub) in komprimierte OGG-Audiodateien um, optional konvertiert es sie direkt in MP3 mit Kapiteltags.
Es nutzt die **Piper TTS Engine** für die Generierung.

Dank Streaming-Mode können auch große Dokumente (z.B. ganze Bücher) effizient in Audio konvertiert werden, ohne den Arbeitsspeicher zu überlasten. 
Die Ausgaben lassen sich direkt mit einem Player wie mpv anhören, während sie erzeugt werden.

## Features
--------

**Breite Formatunterstützung:** Unterstützt Textdateien (.txt), Word (.docx), OpenDocument (.odt) und E-Books (.epub).

**Effiziente Segmentierung:** Der Text wird in Segmente (Kapitel/Abschnitte) zerlegt.

**Kapitel-Marker:** Die präzisen Startzeiten der Segmente werden als Metadaten im OGG-File gespeichert.

**Optionale MP3-Konvertierung:** Konvertierung nach MP3 mit universellen ID3-Kapitel-Tags (`--mp3`).

**Wiederverwendbarkeit:** Bei der MP3-Konvertierung wird ein vorhandenes OGG-File wiederverwendet, um die zeitraubende Sprachsynthese zu überspringen (die präzisen Marker werden aus den OGG-Kommentaren ausgelesen).

**Streaming-Ausgabe:** Audio ist live während der Generierung abspielbar (z.B. mit `mpv`).

**Flexible Wahl der ONNX-Stimme:**  Standard de_DE-thorsten-high.onnx

## Installation
------------
### Python-Abhängigkeiten
   Piper TTS installieren:
   ```python3 -m pip install piper-tts```

   Abhängigkeiten für Textformate:
   ```sudo apt install python3-docx python3-odf python3-soundfile espeak-ng espeak-ng-data ffmpeg```
 

   ```
    pip install -r requirements.txt 
   ```

     beziehungsweise

   ```
    python3 -m pip install piper-tts soundfile python-docx odfpy ebooklib mutagen
   ```

### 2. Externes Tool (FFmpeg)

```
# Auf Debian/Ubuntu-basierten Systemen
sudo apt install ffmpeg 

# Auf macOS (mit Homebrew)
brew install ffmpeg
```


### 3. Stimme herunterladen

Laden Sie eine ONNX-Stimme herunter (z.B. `de_DE-thorsten-high.onnx` und `de_DE-thorsten-high.onnx.json`) und legen Sie sie im Ordner `hoerbuch/models/` ab oder geben --voice  an.
 


### 4. Lokalisierung (optional):
    locales/de/LC_MESSAGES/hoerbuch.po → kompilieren:
     ```
     msgfmt locales/de/LC_MESSAGES/hoerbuch.po -o locales/de/LC_MESSAGES/hoerbuch.mo
     ```
## Benutzung
----------
Das Skript akzeptiert den Dateipfad als erstes Argument.

Basic:
    ./hoerbuch.py <input_file>

Beispiele:
1. Textdatei in OGG konvertieren:
    ./hoerbuch.py README.txt

2. Word-Dokument mit Leerzeichen im Namen:
    ./hoerbuch.py "100 Kieselsteinchen (Band 1).docx"

3. Mit alternativem ONNX-Stimmfile:
    ./hoerbuch.py "100 Kieselsteinchen.docx" --voice models/de_DE-thorsten-low.onnx

### OGG-Generierung (Standard, schnell)
Ausgabe:
- Standardmäßig wird eine OGG-Datei im gleichen Ordner erzeugt, mit gleichem Namen:
  z.B. hoerbuch.txt → hoerbuch.ogg
- Die Datei kann direkt mit mpv oder anderen Playern abgespielt werden:
    mpv "100 Kieselsteinchen (Band 1).ogg"

### 2. MP3-Generierung mit Kapiteln

Führt die Synthese durch und konvertiert direkt in MP3. **Erfordert `ffmpeg`.**

```
./hoerbuch.py --mp3 dokument.epub
# Ausgabe: dokument.mp3 und dokument.ogg
```

### 3. Schnelle MP3-Konvertierung aus vorhandenem OGG

Wenn `dokument.ogg` bereits existiert, wird die Synthese übersprungen und die Marker aus den OGG-Kommentaren ausgelesen.


```
# Vorhandenes dokument.ogg wird für die Konvertierung genutzt:
./hoerbuch.py --mp3 dokument.epub
# Ausgabe: dokument.mp3 (Sehr schnell, da nur Konvertierung und Tagging)
```

### 4. Mit alternativer ONNX-Stimme

```
./hoerbuch.py my_novel.docx --voice models/en_US-kathleen-low.onnx
```
 


## Tipps
-----
- Für sehr große Dokumente (~70.000 Wörter) empfiehlt es sich, die Ausgabe direkt zu streamen und live zu kontrollieren.
- Mehrere aufeinanderfolgende Leerzeilen werden automatisch auf maximal zwei zusammengefasst, um übermäßige Pausen zu vermeiden.
- Fehlermeldungen passen sich an die Systemsprache an (lokalisierbar via gettext).

## Lizenz
-------
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

---

Viel Spaß beim Erstellen von Hörbüchern! 🎧

