# Zielverzeichnis
DIR="../models/"
mkdir -p "$DIR"

# URLs der Dateien
ONNX_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx"
JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx.json"

echo "Lade de_DE-thorsten-high.onnx herunter..."
curl -L "$ONNX_URL" -o "$DIR/de_DE-thorsten-high.onnx"

echo "Lade de_DE-thorsten-high.onnx.json herunter..."
curl -L "$JSON_URL" -o "$DIR/de_DE-thorsten-high.onnx.json"

echo "Download abgeschlossen. Dateien liegen jetzt in $DIR"
