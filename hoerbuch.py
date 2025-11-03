import locale
import sys
import os
import pathlib
import re
import numpy as np
import soundfile as sf
import argparse
import gettext
import subprocess
import logging
from lxml import html

# --- Logging helper ---
def setup_logging(debug=False):
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.ERROR,
        format="%(levelname)s: %(message)s"
    )

# --- Mutagen (MP3 Tagging & OGG Tagging) ---
try:
    import mutagen.mp3
    import mutagen.id3
    import mutagen.oggvorbis
    from mutagen.id3 import CHAP, TIT2, TXXX, WXXX, TPE1, APIC
except ImportError:
    sys.stderr.write("Error: mutagen not installed. Install with: python3 -m pip install mutagen\n")
    sys.exit(1)

# --- Piper import with optional stderr suppression (keep startup noise quiet) ---
try:
    # Detect debug flag early
    DEBUG = "--debug" in sys.argv or "-d" in sys.argv

    if not DEBUG:
        class NullWriter:
            def write(self, *args, **kwargs): pass
            def flush(self, *args, **kwargs): pass

        old_stderr = sys.stderr
        sys.stderr = NullWriter()

    from piper import PiperVoice

    if DEBUG and 'old_stderr' in globals():
        sys.stderr = old_stderr

except ImportError:
    sys.stderr.write("Error: piper-tts not installed. Install with: python3 -m pip install piper-tts\n")
    sys.exit(1)
except Exception as e:
    sys.stderr.write(f"Critical error during Piper import/setup: {e}\n")
    sys.exit(1)

# --- Configuration ---
DEFAULT_MODEL_NAME = "de_DE-thorsten-high.onnx"
if getattr(sys, 'frozen', False):
    # Binary-Modus: Neben der Executable suchen
    SCRIPT_DIR = pathlib.Path(sys.executable).parent
else:
    # Entwicklungs-Modus: Neben der .py Datei suchen  
    SCRIPT_DIR = pathlib.Path(__file__).resolve().parent


SYSTEM_MODEL_DIRS = [
    SCRIPT_DIR / "models",
    pathlib.Path(sys.prefix) / "hoerbuch/models/"
]
LOCAL_DIRS = [
    SCRIPT_DIR / "locales",
    pathlib.Path(sys.prefix) / "share/locale",
]

# --- Localization setup ---
# All user-facing strings must use _() after this setup so xgettext picks them up.
_ = lambda s: s  # fallback

try:
    locale.setlocale(locale.LC_ALL, '')
    current_locale_tuple = locale.getlocale()
    current_locale_code = (current_locale_tuple[0] or "en").split('_')[0]

    t = None
    for localedir in LOCAL_DIRS:
        try:
            t = gettext.translation(
                domain="hoerbuch",
                localedir=str(localedir),
                languages=[current_locale_code],
                fallback=True
            )
            if t:
                break
        except Exception:
            continue

    if t:
        t.install()
        _ = t.gettext

except Exception:
    _ = lambda s: s

# --- Constants ---
SILENCE_PRE_SECONDS = 0.5
SILENCE_POST_SECONDS = 5.0

# --- Document format dependencies ---
try:
    from docx import Document  # used in unified document extractor
except ImportError:
    sys.stderr.write(_("Error: python-docx not found. Install with: sudo apt install python3-docx\n"))
    sys.exit(1)

try:
    from odf.opendocument import load  # used in unified document extractor
    from odf import text as odf_text
except ImportError:
    sys.stderr.write(_("Error: python3-odf not found. Install with: sudo apt install python3-odf\n"))
    sys.exit(1)

try:
    import ebooklib
    from ebooklib import epub
except ImportError:
    sys.stderr.write(_("Error: python3-ebooklib not found. Install with: pip install ebooklib\n"))
    sys.exit(1)

# --- Utility: generate silence array ---
def generate_silence_array(duration_seconds, sample_rate):
    """Return a 1-D int16 numpy array with silence for duration_seconds."""
    num_samples = int(duration_seconds * sample_rate)
    return np.zeros(num_samples, dtype=np.int16)

# --- Title extraction from path ---
def get_title_from_path(input_path):
    """Return a cleaned title from a file path stem."""
    name = input_path.stem
    name = re.sub(r'[_\-\.]', ' ', name)
    name = re.sub(r'\s{2,}', ' ', name).strip()
    title = name.title()
    return title

# --- EPUB extraction ---
def extract_segments_from_epub(input_path):
    """Extract segments from EPUB using TOC order and return (segments, metadata)."""
    import time
    t0 = time.time()
    book = epub.read_epub(input_path)

    metadata = {
        "title": book.get_metadata("DC", "title")[0][0] if book.get_metadata("DC", "title") else input_path.stem,
        "artist": book.get_metadata("DC", "creator")[0][0] if book.get_metadata("DC", "creator") else "Unknown"
    }

    segments = []
    content_cache = {}

    def fast_extract_text(xhtml_bytes):
        try:
            doc = html.fromstring(xhtml_bytes)
            texts = doc.xpath('//body//text()')
            return " ".join(t.strip() for t in texts if t.strip())
        except Exception:
            return ""

    for toc_entry in book.toc:
        if isinstance(toc_entry, tuple):
            toc_entry = toc_entry[0]

        href = getattr(toc_entry, "href", None)
        title = getattr(toc_entry, "title", None) or os.path.basename(href or "")

        if not href:
            continue

        if href in content_cache:
            text_content = content_cache[href]
        else:
            item = book.get_item_with_href(href)
            if not item:
                continue
            text_content = fast_extract_text(item.content)
            content_cache[href] = text_content

        if text_content.strip():
            segments.append((title, text_content))

    print(f"[DEBUG] EPUB extraction done in {time.time() - t0:.2f}s, {len(segments)} segments")
    return segments, metadata

# --- TXT extraction ---
def extract_segments_from_txt(path):
    """Segment text file by paragraphs (two or more newlines)."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    segments = [(_("Segment {n}").format(n=i+1), p) for i, p in enumerate(paragraphs)]
    return segments, {}

# --- Unified DOCX/ODT extractor ---
def extract_segments_from_document(file_path):
    """
    Unified extractor for .docx and .odt documents.

    Detects chapters from headings (Heading 1–3) and groups following paragraphs.
    Returns (segments, metadata).
    """
    ext = pathlib.Path(file_path).suffix.lower()
    segments = []
    current_title = None
    current_text = []

    metadata = {"title": None, "author": None}

    if ext == ".docx":
        doc = Document(file_path)
        for p in doc.paragraphs:
            style = p.style.name if p.style else ""
            text = p.text.strip()
            if not text:
                continue
            if style.startswith("Heading") or style.startswith("Überschrift"):
                if current_title and current_text:
                    segments.append((current_title, "\n".join(current_text).strip()))
                current_title = text
                current_text = []
            else:
                current_text.append(text)

        if current_title and current_text:
            segments.append((current_title, "\n".join(current_text).strip()))
        elif not segments and current_text:
            segments = [(pathlib.Path(file_path).stem, "\n".join(current_text).strip())]

        props = doc.core_properties
        if props.title:
            metadata["title"] = props.title
        if props.author:
            metadata["author"] = props.author

    elif ext == ".odt":
        doc = load(str(file_path))
        paragraphs = doc.getElementsByType(odf_text.P)
        for p in paragraphs:
            text_content = "".join(t.data for t in p.childNodes if t.nodeType == t.TEXT_NODE).strip()
            style_name = p.getAttribute("stylename") or ""
            if not text_content:
                continue
            if style_name.lower().startswith("heading") or "überschrift" in style_name.lower():
                if current_title and current_text:
                    segments.append((current_title, "\n".join(current_text).strip()))
                current_title = text_content
                current_text = []
            else:
                current_text.append(text_content)

        if current_title and current_text:
            segments.append((current_title, "\n".join(current_text).strip()))
        elif not segments and current_text:
            segments = [(pathlib.Path(file_path).stem, "\n".join(current_text).strip())]

        meta = doc.meta
        if hasattr(meta, "title") and meta.title:
            metadata["title"] = meta.title
        if hasattr(meta, "creator") and meta.creator:
            metadata["author"] = meta.creator

    else:
        raise ValueError(f"Unsupported document type: {ext}")

    if not metadata["title"]:
        metadata["title"] = pathlib.Path(file_path).stem
    if not metadata["author"]:
        metadata["author"] = "Unknown"

    return segments, metadata

# === Chapter mode handler ===
def run_chapter_logic(segments, cli_chapters_value, input_path, model_path, metadata, args):
    """
    Handle chapter mode behavior.

    cli_chapters_value: False | True | int
    """
    gettext_func = globals().get('_', lambda s: s)
    num_chapters = len(segments)

    # Direct mode: integer chapter
    if isinstance(cli_chapters_value, int):
        idx = cli_chapters_value
        if 1 <= idx <= num_chapters:
            title, text = segments[idx - 1]
            print(gettext_func("\n[Chapter mode: direct chapter {n} - '{title}']").format(n=idx, title=title))
            safe_file_name = safe_filename(title, idx)
            out_ogg = input_path.parent / f"{input_path.stem}_{safe_file_name}.ogg"
            final_out = out_ogg.with_suffix(".mp3") if args.mp3 else out_ogg
            if final_out.exists():
                print(gettext_func("Warning: output file already exists: {file}").format(file=final_out.name))
                return
            synthesize_separate_chapter(title, text, model_path, out_ogg, metadata, args.speed, args.mp3)
            return
        else:
            print(gettext_func("Warning: chapter {n} not found (document has {m} chapters).").format(n=idx, m=num_chapters))
            cli_chapters_value = True  # fall back to interactive

    # Interactive mode
    if cli_chapters_value is True:
        print(gettext_func("\n✨ Interactive chapter mode started ✨"))
        print(gettext_func("{n} chapters detected:").format(n=num_chapters))
        for i, (title, _) in enumerate(segments, 1):
            print(f"  [{i}] {title}")

        print(gettext_func("\nOptions:"))
        print(gettext_func("  [a] All chapters in ONE OGG file (with chapter markers)"))
        print(gettext_func("  [s] Split chapters: ONE file per chapter"))
        print(gettext_func("  [<number>] Synthesize a single specific chapter (e.g. '2')"))
        print("-" * 50)

        selection = input(gettext_func("Your choice: ")).strip().lower()

        if selection == "a":
            print(gettext_func("\n→ Synthesizing all chapters into a combined OGG..."))
            text_to_ogg(segments, model_path, str(input_path.with_suffix(".ogg")), metadata, args.speed)
            if args.mp3:
                convert_ogg_to_mp3(input_path.with_suffix(".ogg"), input_path.with_suffix(".mp3"))
            print(gettext_func("✅ Combined synthesis finished."))
            return

        if selection == "s":
            print(gettext_func("\n→ Synthesizing each chapter to separate files..."))
            base_path = input_path.parent
            base_name = input_path.stem
            for i, (title, text) in enumerate(segments, 1):
                safe_file_name = safe_filename(title, i)
                ogg_chapter_path = base_path / f"{base_name}_{safe_file_name}.ogg"
                mp3_chapter_path = ogg_chapter_path.with_suffix(".mp3")
                final_output = mp3_chapter_path if args.mp3 else ogg_chapter_path
                if final_output.exists():
                    print(gettext_func("Skipping chapter '{title}': output file '{file}' already exists.").format(title=title, file=final_output.name))
                    continue
                try:
                    synthesize_separate_chapter(title, text, model_path, ogg_chapter_path, metadata, args.speed, args.mp3)
                except Exception as e:
                    sys.stderr.write(gettext_func("Error synthesizing chapter {n} ('{title}'): {msg}\n").format(n=i, title=title, msg=e))
                    if ogg_chapter_path.exists(): os.remove(ogg_chapter_path)
                    if mp3_chapter_path.exists(): os.remove(mp3_chapter_path)
            print(gettext_func("✅ All chapters processed in split-file mode."))
            return

        if selection.isdigit():
            idx = int(selection)
            if 1 <= idx <= num_chapters:
                title, text = segments[idx - 1]
                safe_file_name = safe_filename(title, idx)
                out_ogg = input_path.parent / f"{input_path.stem}_{safe_file_name}.ogg"
                final_out = out_ogg.with_suffix(".mp3") if args.mp3 else out_ogg
                if final_out.exists():
                    print(gettext_func("Warning: output file already exists: {file}").format(file=final_out.name))
                    return
                synthesize_separate_chapter(title, text, model_path, out_ogg, metadata, args.speed, args.mp3)
                print(gettext_func("✅ Single chapter finished."))
            else:
                print(gettext_func("Warning: chapter {n} not found (document has {m} chapters).").format(n=idx, m=num_chapters))
            return

        print(gettext_func("Invalid selection, aborting."))
        return

    # Not in chapter mode -> caller continues single-file synthesis
    print(gettext_func("Continuing with standard single-file synthesis (no chapter mode)."))
    return

# --- Streaming TTS to OGG + markers (single-file output) ---
def text_to_ogg(segments, model_path, output_file, metadata, speed_rate: float = 1.0):
    """Stream audio using Piper, capture precise marker times and write OGG file."""
    print(_("Loading voice from: {file}").format(file=model_path))
    voice = PiperVoice.load(model_path)
    sample_rate = voice.config.sample_rate

    if speed_rate != 1.0:
        voice.config.speed = speed_rate
        print(_("-> TTS speed adjusted to: {speed} (1.0 = normal)").format(speed=speed_rate))

    total_chars = sum(len(text) for _, text in segments)
    logging.debug(_("Synthesizing ({n} characters in {m} segments)...").format(n=total_chars, m=len(segments)))

    markers = []
    current_time_seconds = 0.0

    pre_silence_array = generate_silence_array(SILENCE_PRE_SECONDS, sample_rate)
    post_silence_array = generate_silence_array(SILENCE_POST_SECONDS, sample_rate)

    with sf.SoundFile(
        output_file,
        mode="w",
        samplerate=sample_rate,
        channels=1,
        format="OGG",
        subtype="VORBIS",
    ) as f:
        f.write(pre_silence_array)
        current_time_seconds += SILENCE_PRE_SECONDS

        for title, text_content in segments:
            markers.append({'time_seconds': current_time_seconds, 'title': title})
            print(_("  -> Segment started: {title} at {time:.2f}s").format(title=title, time=current_time_seconds))

            paragraphs = [p for p in text_content.split("\n\n") if p.strip()]
            if not paragraphs:
                paragraphs = [text_content]

            for para in paragraphs:
                for chunk in voice.synthesize(para):
                    f.write(chunk.audio_int16_array)
                    chunk_duration_seconds = len(chunk.audio_int16_array) / sample_rate
                    current_time_seconds += chunk_duration_seconds

        f.write(post_silence_array)
        current_time_seconds += SILENCE_POST_SECONDS

    try:
        audio = mutagen.oggvorbis.OggVorbis(output_file)
        audio['title'] = [metadata.get('title', _('Unknown Title'))]
        audio['artist'] = [metadata.get('artist', _('Piper TTS'))]

        keys_to_delete = [k for k in audio.keys() if k.startswith('chapter_')]
        for k in keys_to_delete:
            del audio[k]

        for i, marker in enumerate(markers):
            audio[f'chapter_start_time_{i}'] = [str(marker['time_seconds'])]
            audio[f'chapter_title_{i}'] = [marker['title']]

        audio.save()
        print(_("✅ Chapter markers and metadata written to OGG Vorbis comments."))
    except Exception as e:
        sys.stderr.write(_("Warning: Failed to write OGG Vorbis markers: {msg}\n").format(msg=e))

    print(_("✅ OGG file successfully written: {file}").format(file=output_file))
    print(_("Total duration: {time:.2f}s").format(time=current_time_seconds))
    return markers

# --- Read custom OGG markers ---
def read_ogg_markers(ogg_path):
    """Read custom chapter markers from OGG Vorbis comments."""
    print(_("Attempting to read custom markers from existing OGG file..."))
    markers = []
    try:
        audio = mutagen.oggvorbis.OggVorbis(ogg_path)
        i = 0
        while True:
            time_key = f'chapter_start_time_{i}'
            title_key = f'chapter_title_{i}'
            if time_key in audio and title_key in audio:
                time_s = float(audio[time_key][0])
                title = audio[title_key][0]
                markers.append({'time_seconds': time_s, 'title': title})
                i += 1
            else:
                break
        if markers:
            print(_("✅ Successfully read {n} precise markers from OGG file.").format(n=len(markers)))
            return markers
    except Exception:
        return None
    return None

# --- Approximate markers fallback ---
def calculate_approximate_markers(segments, ogg_path):
    """Estimate chapter start times proportionally by text length."""
    print(_("Calculating approximate markers from existing OGG file..."))
    try:
        with sf.SoundFile(ogg_path, 'r') as f:
            total_ogg_duration = f.frames / f.samplerate
    except Exception as e:
        sys.stderr.write(_("Error reading OGG duration for marker calculation: {msg}\n").format(msg=e))
        return []

    fixed_silence_duration = SILENCE_PRE_SECONDS + SILENCE_POST_SECONDS
    tts_duration = max(0, total_ogg_duration - fixed_silence_duration)
    total_chars = sum(len(text) for _, text in segments)
    if total_chars == 0 or tts_duration == 0:
        return []

    current_time_seconds = SILENCE_PRE_SECONDS
    markers = []
    for title, text_content in segments:
        markers.append({'time_seconds': current_time_seconds, 'title': title})
        char_ratio = len(text_content) / total_chars
        segment_duration = tts_duration * char_ratio
        current_time_seconds += segment_duration
        print(_("  -> Approximate segment start: {title} at {time:.2f}s").format(title=title, time=markers[-1]['time_seconds']))

    print(_("Total approximate duration used for calculation: {time:.2f}s").format(time=current_time_seconds + SILENCE_POST_SECONDS - SILENCE_PRE_SECONDS))
    return markers

# --- FFmpeg check and conversion ---
def check_ffmpeg_installed():
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.stderr.write(_("Fatal: ffmpeg is required for MP3 conversion but was not found. Please install ffmpeg.\n"))
        return False

def convert_ogg_to_mp3(ogg_path, mp3_path, delete_ogg=True):
    print(_("Converting OGG to MP3 (CBR 320k)..."))
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i", str(ogg_path),
                "-codec:a", "libmp3lame",
                "-b:a", "320k",
                "-ac", "2",
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                str(mp3_path)
            ],
            check=True
        )
        print(_("✅ MP3 file successfully converted: {file}").format(file=mp3_path))
        if delete_ogg:
            os.remove(ogg_path)
            print(_("→ Temporary OGG file deleted: {file}").format(file=ogg_path))
        return True
    except subprocess.CalledProcessError as e:
        sys.stderr.write(_("Error during MP3 conversion (ffmpeg failed): {msg}\n").format(msg=e))
        return False
    except FileNotFoundError:
        sys.stderr.write(_("Error: ffmpeg command not found.\n"))
        return False

def write_mp3_chapter_tags(mp3_path, markers, metadata):
    print(_("Writing chapter markers and metadata to MP3..."))
    try:
        audio = mutagen.mp3.MP3(mp3_path)
        audio.tags = mutagen.id3.ID3()

        book_title = metadata.get('title', _('Unknown Title'))
        book_artist = metadata.get('artist', _('Piper TTS'))

        audio.tags.add(TIT2(encoding=3, text=[book_title]))
        audio.tags.add(TPE1(encoding=3, text=[book_artist]))

        chapter_frame_id = 0
        for marker in markers:
            chapter_frame_id += 1
            start_ms = int(marker['time_seconds'] * 1000)
            if chapter_frame_id < len(markers):
                end_ms = int(markers[chapter_frame_id]['time_seconds'] * 1000)
            else:
                end_ms = 0
            chap = CHAP(
                element_id=f"chp_{chapter_frame_id}".encode('latin-1'),
                start_time=start_ms,
                end_time=end_ms,
                start_offset=0,
                end_offset=0
            )
            sub_title = TIT2(encoding=3, text=[marker['title']])
            chap.subframes = {'TIT2': sub_title}
            audio.tags.add(chap)

        audio.save(v2_version=3)
        print(_("✅ Metadata written successfully (Title: '{title}', Artist: '{artist}').").format(title=book_title, artist=book_artist))
    except Exception as e:
        sys.stderr.write(_("Error writing MP3 chapter tags: {msg}\n").format(msg=e))
        sys.stderr.write(_("Please ensure required libraries are installed and the file is valid.\n"))
        return False
    return True

# --- Single chapter synthesis helper ---
def safe_filename(title, counter):
    safe_name = re.sub(r'[^\w\s\-]', '', title).strip()
    safe_name = re.sub(r'\s+', '_', safe_name)
    safe_name = safe_name[:50]
    return f"{counter:02d}_{safe_name}"

def synthesize_separate_chapter(title, text_content, model_path, output_path, metadata, speed_rate, convert_to_mp3):
    voice = PiperVoice.load(model_path)
    sample_rate = voice.config.sample_rate
    if speed_rate != 1.0:
        voice.config.speed = speed_rate

    current_time_seconds = 0.0
    pre_silence_array = generate_silence_array(SILENCE_PRE_SECONDS, sample_rate)
    post_silence_array = generate_silence_array(SILENCE_POST_SECONDS, sample_rate)

    print(_("  -> Synthesizing chapter: '{title}'").format(title=title))
    with sf.SoundFile(
        str(output_path),
        mode="w",
        samplerate=sample_rate,
        channels=1,
        format="OGG",
        subtype="VORBIS",
    ) as f:
        f.write(pre_silence_array)
        current_time_seconds += SILENCE_PRE_SECONDS

        paragraphs = [p for p in text_content.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text_content]

        for para in paragraphs:
            for chunk in voice.synthesize(para):
                f.write(chunk.audio_int16_array)
                chunk_duration_seconds = len(chunk.audio_int16_array) / sample_rate
                current_time_seconds += chunk_duration_seconds

        f.write(post_silence_array)
        current_time_seconds += SILENCE_POST_SECONDS

    print(_("  -> OGG saved: {file} (Duration: {time:.2f}s)").format(file=output_path.name, time=current_time_seconds))

    try:
        audio = mutagen.oggvorbis.OggVorbis(str(output_path))
        audio['title'] = [title]
        audio['artist'] = [metadata.get('artist', _('Piper TTS'))]
        audio.save()
    except Exception as e:
        sys.stderr.write(_("Warning: Failed to write OGG Vorbis metadata for single chapter: {msg}\n").format(msg=e))

    if convert_to_mp3:
        mp3_path = output_path.with_suffix(".mp3")
        if convert_ogg_to_mp3(output_path, mp3_path, delete_ogg=True):
            try:
                mp3_audio = mutagen.mp3.MP3(mp3_path)
                mp3_audio.tags = mutagen.id3.ID3()
                mp3_audio.tags.add(TIT2(encoding=3, text=[title]))
                mp3_audio.tags.add(TPE1(encoding=3, text=[metadata.get('artist', _('Piper TTS'))]))
                mp3_audio.save(v2_version=3)
                print(_("  -> MP3 tagged: {file}").format(file=mp3_path.name))
            except Exception as e:
                sys.stderr.write(_("Error writing simple MP3 tags: {msg}\n").format(msg=e))

# --- Find model path ---
def find_model_path(voice_arg):
    if voice_arg:
        explicit_path = pathlib.Path(voice_arg)
        if explicit_path.exists():
            return str(explicit_path)
        sys.stderr.write(_("Warning: Explicit voice file not found at '{file}'. Trying defaults...\n").format(file=voice_arg))

    for model_dir in SYSTEM_MODEL_DIRS:
        model_path = model_dir / DEFAULT_MODEL_NAME
        if model_path.exists():
            print(_("Using voice from: {file}").format(file=model_path))
            return str(model_path)

    sys.stderr.write(_("Fatal: Voice model '{file}' not found in any path (including script/models and install dir).\n").format(file=DEFAULT_MODEL_NAME))
    sys.exit(1)

# --- Main program (no shebang, gettext-friendly, position-independent -k) ---
def main():
    parser = argparse.ArgumentParser(
        description=_("Convert text documents (.txt, .docx, .odt, .epub) to OGG audio using Piper TTS, with optional MP3 conversion and chapter control."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_(
            "Examples:\n"
            "  %(prog)s book.epub                    # Convert EPUB to OGG\n"
            "  %(prog)s -m -s 0.9 document.docx      # Convert to MP3 with slower speed\n"
            "  %(prog)s book.epub -k -1              # Interactive chapter selection\n"
            "  %(prog)s book.epub -k 3               # Convert only chapter 3\n"
            "  %(prog)s -k 3 book.epub               # Also accepted (position independent)\n"
        )
    )

    parser.add_argument("-d", "--debug", action="store_true", help=_("Show debug messages"))
    parser.add_argument("input_file", type=str, help=_("Input file path (.txt, .docx, .odt, .epub)"))
    parser.add_argument("--voice", type=str, default=None, help=_("Optional ONNX voice file path"))
    parser.add_argument("-m", "--mp3", action="store_true", help=_("Convert OGG output to MP3 format with chapter tags (requires ffmpeg)"))
    parser.add_argument("-s", "--speed", type=float, default=1.0, help=_("TTS speech rate multiplier (1.0 = normal, 0.9 = slower)"))

    # parse raw string for -k and normalize later
    parser.add_argument("-k", "--chapters",
                        nargs="?",
                        const=True,
                        type=str,
                        default=False,
                        help=_("Interactive (-k) or direct chapter (e.g. -k 5). Position independent."))

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Setup logging according to debug flag
    setup_logging(debug=args.debug)

    # Normalize chapter argument robustly
    chapters_raw = args.chapters
    chapter_value = False
    if isinstance(chapters_raw, str):
        try:
            chapter_value = int(chapters_raw)
        except ValueError:
            if os.path.exists(chapters_raw):
                if not os.path.exists(args.input_file):
                    # user likely passed file to -k; swap and enable interactive
                    args.input_file, chapters_raw = chapters_raw, args.input_file
                    chapter_value = True
                else:
                    # both exist: prefer interactive
                    chapter_value = True
            else:
                chapter_value = True
    elif chapters_raw is True:
        chapter_value = True
    else:
        chapter_value = False

    args.chapters = chapter_value

    input_path = pathlib.Path(args.input_file)
    if not input_path.exists():
        sys.stderr.write(_("Error: Input file '{file}' not found.\n").format(file=input_path))
        sys.exit(1)

    model_path = find_model_path(args.voice)

    ogg_path = input_path.with_suffix(".ogg")
    mp3_path = input_path.with_suffix(".mp3")
    if args.mp3 and not check_ffmpeg_installed():
        sys.exit(1)

    ext = input_path.suffix.lower()
    segments, extracted_metadata = [], {}
    try:
        if ext == ".txt":
            print(_("TXT detected. Extracting segments..."))
            segments, extracted_metadata = extract_segments_from_txt(input_path)
        elif ext in (".docx", ".odt"):
            print(_(f"{ext.upper()} detected. Extracting segments..."))
            segments, extracted_metadata = extract_segments_from_document(input_path)
        elif ext == ".epub":
            print(_("EPUB detected. Extracting chapters..."))
            segments, extracted_metadata = extract_segments_from_epub(input_path)
        else:
            sys.stderr.write(_("Error: Unsupported file extension '{ext}'. Supported: .txt, .docx, .odt, .epub.\n").format(ext=ext))
            sys.exit(1)
    except Exception as e:
        sys.stderr.write(_("Error during document parsing: {msg}\n").format(msg=e))
        sys.exit(1)

    if not segments:
        print(_("Warning: Document contains no extractable text segments."))
        sys.exit(0)

    metadata = {
        "title": extracted_metadata.get("title") or get_title_from_path(input_path),
        "artist": extracted_metadata.get("artist") or _("Piper TTS")
    }
    print(_("Using title: '{title}', artist: '{artist}'").format(title=metadata["title"], artist=metadata["artist"]))

    if args.chapters:
        run_chapter_logic(segments, args.chapters, input_path, model_path, metadata, args)
        return

    final_output_path = mp3_path if args.mp3 else ogg_path
    if final_output_path.exists():
        print(_("🛑 Output file '{file}' already exists. Skipping synthesis/conversion.").format(file=final_output_path))
        print(_("→ Please rename or delete the existing file if you wish to regenerate the audio."))
        sys.exit(1)

    try:
        markers = []
        synthesize_needed = True

        if args.mp3 and ogg_path.exists():
            print(_("Existing OGG file found. Reusing for fast MP3 conversion."))
            markers = read_ogg_markers(ogg_path)
            if markers:
                synthesize_needed = False
                print(_("→ Using precise markers from OGG for MP3 tagging."))
            else:
                print(_("→ Warning: No OGG markers found. Estimating markers from text length."))
                markers = calculate_approximate_markers(segments, ogg_path)
                synthesize_needed = False

        if synthesize_needed:
            markers = text_to_ogg(segments, model_path, str(ogg_path), metadata, args.speed)

        if args.mp3:
            if convert_ogg_to_mp3(ogg_path, mp3_path, delete_ogg=synthesize_needed):
                write_mp3_chapter_tags(mp3_path, markers, metadata)

    except Exception as e:
        sys.stderr.write(_("Critical error: {msg}\n").format(msg=e))
        if args.debug and "old_stderr" in globals():
            import traceback
            traceback.print_exc(file=old_stderr)

        if ogg_path.exists() and synthesize_needed:
            os.remove(ogg_path)
            print(_("→ Temporary OGG file deleted after error."))
        if mp3_path.exists() and args.mp3:
            os.remove(mp3_path)
            print(_("→ Partial MP3 file deleted after error."))

        sys.exit(1)

if __name__ == "__main__":
    main()

