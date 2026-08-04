import csv
import json
import os
from pathlib import Path
import shutil
import zipfile

# Config
CSV_PATH = 'keyword_map.csv'
OUTPUT_DIR = Path('soundpack_export')
OUTPUT_JSON = 'soundpack.json'
OUTPUT_ZIP = 'soundpack.zip'
DEFAULT_COOLDOWN = 420
AUDIO_EXTS = ['.mp3', '.wav']

# Prompt user for base folder
sound_base = input('Enter the path to the folder containing all your sound files and folders: ').strip()
SOUNDS_BASE = Path(sound_base)
if not SOUNDS_BASE.is_dir():
    print(f"Error: '{SOUNDS_BASE}' is not a valid directory.")
    exit(1)

if OUTPUT_DIR.exists():
    shutil.rmtree(OUTPUT_DIR)
OUTPUT_DIR.mkdir()

triggers = []
used_files = set()
missing_files = []
missing_folders = []

with open(CSV_PATH, newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    for row in reader:
        if not row or not row[0].strip():
            continue
        # Parse triggers (may be quoted and comma-separated)
        trigger_col = row[0].strip().strip('"')
        trigger_words = [w.strip() for w in trigger_col.split(',') if w.strip()]
        # Sound reference
        sound_ref = row[1].strip().replace('sounds\\', '').replace('sounds/', '')
        # Cooldown (optional, default 10)
        cooldown = DEFAULT_COOLDOWN
        if len(row) > 2:
            try:
                val = int(row[2])
                cooldown = val
            except (ValueError, TypeError):
                cooldown = DEFAULT_COOLDOWN
        # Determine if this is a folder (randomsound_*.py) or a single file
        sounds_list = []
        if sound_ref.endswith('.py'):
            folder_name = sound_ref.replace('randomsound_', '').replace('.py', '')
            folder_path = SOUNDS_BASE / folder_name
            out_folder_path = OUTPUT_DIR / folder_name
            if folder_path.is_dir():
                out_folder_path.mkdir(exist_ok=True)
                found = False
                for f in sorted(folder_path.iterdir()):
                    if f.suffix.lower() in AUDIO_EXTS and f.is_file():
                        rel_path = f'{folder_name}/{f.name}'
                        out_path = OUTPUT_DIR / folder_name / f.name
                        shutil.copy2(f, out_path)
                        sounds_list.append({'name': rel_path})
                        used_files.add(rel_path)
                        found = True
                if not found:
                    print(f'[WARN] No audio files found in folder: {folder_path}')
                    missing_folders.append(str(folder_path))
            else:
                print(f'[WARN] Missing random folder: {folder_path}')
                missing_folders.append(str(folder_path))
        else:
            # Always look for single sounds in 'sounds/sounds/'
            file_path = SOUNDS_BASE / 'sounds' / sound_ref
            if file_path.is_file():
                rel_path = f'sounds/{sound_ref}'
                out_path = OUTPUT_DIR / 'sounds' / sound_ref
                out_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, out_path)
                sounds_list.append({'name': rel_path})
                used_files.add(rel_path)
            else:
                print(f'[WARN] Missing single sound: {file_path}')
                missing_files.append(str(file_path))
        # For each trigger/alias, create a trigger entry
        for word in trigger_words:
            triggers.append({
                'word': word,
                'sounds': sounds_list,
                'cooldown': cooldown
            })

# Write manifest
with open(OUTPUT_DIR / OUTPUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(triggers, f, indent=2)

# Zip the output directory
with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for file in files:
            file_path = Path(root) / file
            arcname = file_path.relative_to(OUTPUT_DIR)
            zipf.write(file_path, arcname)

print(f"Soundpack created! {len(triggers)} triggers, {len(used_files)} unique sound files.")
if missing_files:
    print(f"Missing files: {missing_files}")
if missing_folders:
    print(f"Missing or empty folders: {missing_folders}")
print(f"Your distributable soundpack is '{OUTPUT_ZIP}'. Share this zip for import!")
