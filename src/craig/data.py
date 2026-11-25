from http.client import CONFLICT
from pathlib import Path
from collections import defaultdict
from difflib import get_close_matches

import csv
from datetime import datetime

SRC_PATH = Path(__file__).resolve()
MAIN_PATH = SRC_PATH.parents[2]
IMAGE_DIR = MAIN_PATH / "images"
IMAGE_LAYERS = {"Low-res":"lr","Low-res (with host and contours)": "lr-info","High-res": "hr","High-res (with splines)": "hr-info"}
MORPHOLOGIES = {
    "Wide-angle tail": "WAT",
    "Narrow-angle tail": "NAT",
    "Head-tail": "HT",
    "Single-sided": "SS",
    "Straight": "STR",
    "FR1": "FR1",
    "FR2": "FR2",
    "Asymmetric Hybrid": "ASYM",
    "Symmetric Hybrid": "SYM",
}

MORPH_LOOKUP = {}
for name, code in MORPHOLOGIES.items():
    MORPH_LOOKUP[name.lower()] = code   # "wide-angle tail" -> "WAT"
    MORPH_LOOKUP[code.lower()] = code   # "wat" -> "WAT"

SB_MORPHOLOGIES = ["FR1","FR2","ASYM","SYM"]
CONFLICT_MORPHOLOGIES = ["WAT","NAT","STR","SS","HT"]

CSV_FIELDS = ["source_id","morph_1","morph_2","confidence","timestamp"]
CSV_PATH = MAIN_PATH / "data" / "craig_data.csv"

def get_all_sources():
    source_dirs = [x for x in sorted(IMAGE_DIR.iterdir()) if x.is_dir()]
    source_dict = {f.name: f for f in source_dirs}
    return source_dict

def get_source_images(source_id):
    """Gets each image layer PNG associated with a source id"""
    source_dir = IMAGE_DIR / source_id
    if not source_dir.is_dir():
        raise FileNotFoundError(f"source image directory: {source_dir} not found!")
    image_paths = {}
    for layer in IMAGE_LAYERS.values():
        im_path = source_dir / f"{layer}.png"
        if im_path.is_file():
            image_paths[layer] = im_path
        else:
            print(f"Missing {layer} image for source: {source_id}")
            image_paths[layer] = None
    return image_paths

def get_closest_morph(entry):
    entry = entry.strip().lower()

    if len(entry) < 2:
        print(f"Entry: {entry} is too short to match")
        return None

    if entry in MORPH_LOOKUP: #exact match
        return MORPH_LOOKUP[entry]

    codes = {code for key, code in MORPH_LOOKUP.items() if key.startswith(entry)}
    if len(codes) == 1:
        return codes.pop()
    if len(codes) > 1:
        print(f"Ambiguous: {sorted(codes)}")
        return None
    
    match = get_close_matches(entry,list(MORPH_LOOKUP),n=1,cutoff=0.8) #difflib autocorrect
    if len(match) > 0:
        return MORPH_LOOKUP[match[0]]
    else:
        return None

def validate_morphology(entries):
    has_required = any(m in SB_MORPHOLOGIES for m in entries)
    if not has_required:
        msg = f"Classification requires one of the following four morphologies: {SB_MORPHOLOGIES}"
        return False,msg
    
    has_conflict_bt = True if len(set(CONFLICT_MORPHOLOGIES) & set(entries)) > 1 else False 
    if has_conflict_bt:
        msg = f"Entries: {entries} contain more than one bent-tail morphology"
        return False,msg

    has_conflict_sb = True if len(set(SB_MORPHOLOGIES) & set(entries)) > 1 else False 
    if has_conflict_sb:
        msg = f"Entries: {entries} contain more than one surface-brightness morphology"
        return False,msg

    return True,"" 

def write_to_csv(data_dict):
    new_file = not CSV_PATH.is_file()
    time = datetime.now().isoformat(timespec="seconds")
    data_dict["timestamp"] = time
    with open(CSV_PATH, mode="a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(data_dict)

def get_saved_ids():
    all_ids = list(k for k in get_all_sources().keys())
    saved_ids = set()
    if CSV_PATH.exists():
        with open(CSV_PATH, mode="r", newline="", encoding="utf-8") as csv_file:
            saved_ids = {d["source_id"] for d in list(csv.DictReader(csv_file))}

    todo = [s for s in all_ids if s not in saved_ids]
    return todo,saved_ids