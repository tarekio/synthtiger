#!/usr/bin/env python3
"""Convert a polygon ground-truth file to JSON mapping and split dataset.

Usage:
    python3 tools/polygon_gt_to_json.py results/gt.txt results

Behavior:
- Parses lines containing: image_path, dimensions, polygons data.
- Calculates SHA256 hash of images.
- Splits the dataset into train and val subfolders.
- Moves images to results/train/images and results/val/images.
- Writes results/train/labels.json and results/val/labels.json with format:
    {
        "filename": {
            "img_dimensions": [w, h],
            "img_hash": "sha256...",
            "polygons": [[[x,y], ...], ...]
        }
    }
- Uses multiprocessing for hashing and moving files.
"""
import argparse
import json
import os
import sys
import random
import shutil
import ast
import hashlib
from multiprocessing import Pool, cpu_count
from typing import Optional, Tuple, Dict, Any

# helper used by worker processes (must be picklable / top-level)
def resolve_hash_and_move(task: Tuple[str, str, str, str, str]) -> Tuple[str, bool, Optional[str], str]:
    """
    task: (orig_path, orig_basename, new_basename, input_dir, dest_images_dir)
    returns: (new_basename, moved_bool, sha256_hash, message)
    """
    orig_path, orig_basename, new_basename, input_dir, dest_images_dir = task

    # resolve source path
    def find_source(orig_path_local: str, basename_local: str, input_dir_local: str) -> Optional[str]:
        if os.path.isabs(orig_path_local):
            cand = orig_path_local
            if os.path.exists(cand):
                return cand
        else:
            cand = os.path.join(input_dir_local, orig_path_local)
            if os.path.exists(cand):
                return cand
            cand = os.path.join(os.getcwd(), orig_path_local)
            if os.path.exists(cand):
                return cand
            # Recursive search (fallback)
            for root, _, files in os.walk(input_dir_local):
                if basename_local in files:
                    return os.path.join(root, basename_local)
        return None

    try:
        src = find_source(orig_path, orig_basename, input_dir)
        if not src:
            return (new_basename, False, None, f"source not found (orig: {orig_path})")
            
        # Calculate SHA256 hash
        sha256_hash = hashlib.sha256()
        with open(src, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        img_hash = sha256_hash.hexdigest()

        dst = os.path.join(dest_images_dir, new_basename)
        # ensure destination dir exists
        os.makedirs(dest_images_dir, exist_ok=True)
        
        # avoid overwriting existing destination
        if os.path.exists(dst):
            # We return the hash and allow the entry to be added to JSON, but mark move as False
            return (new_basename, False, img_hash, f"destination exists: {dst}")
        
        # attempt move
        shutil.move(src, dst)
        return (new_basename, True, img_hash, f"moved {src} -> {dst}")
    except Exception as e:
        return (new_basename, False, None, f"error: {e}")

def load_json_if_exists(path: str) -> Dict[str, Any]:
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode {path}. Starting fresh.", file=sys.stderr)
    return {}

def get_max_id(mapping: dict) -> int:
    """Finds the highest numeric ID in the existing filenames to resume from."""
    max_id = 0
    for fname in mapping.keys():
        base = os.path.splitext(fname)[0]
        if base.isdigit():
            max_id = max(max_id, int(base))
    return max_id


def convert(input_dir: str, outdir: str, split: float = 0.7, seed: int | None = 42, start_id: int | None = None):
    # Data storage
    temp_data = {} 
    
    duplicates = 0
    total = 0
    bad_lines = 0
    coords_file = os.path.join(input_dir, 'coords.txt')
    gt_file = os.path.join(input_dir, 'gt.txt')

    # 1. Prepare Directories
    train_dir = os.path.join(outdir, 'train')
    val_dir = os.path.join(outdir, 'val')
    os.makedirs(train_dir, exist_ok=True)
    os.makedirs(val_dir, exist_ok=True)

    train_json_path = os.path.join(train_dir, 'labels.json')
    val_json_path = os.path.join(val_dir, 'labels.json')

    # 2. Load Existing Data
    existing_train_map = load_json_if_exists(train_json_path)
    existing_val_map = load_json_if_exists(val_json_path)

    # 3. Determine Starting ID
    if start_id is None or start_id < 0:
        max_train = get_max_id(existing_train_map)
        max_val = get_max_id(existing_val_map)
        current_id = max(max_train, max_val) + 1
        print(f"Auto-detected starting ID: {current_id}")
    else:
        current_id = start_id
        print(f"Using manual starting ID: {current_id}")

    print(f"Reading {gt_file}...")
    gt_dict = {}
    if os.path.exists(gt_file):
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    gt_dict[parts[0]] = parts[1]


    print(f"Reading {coords_file}...")
    with open(coords_file, 'r', encoding='utf-8') as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.rstrip('\n')
            if not line:
                continue
            total += 1
            
            # Parsing logic: try splitting by tab, then by space
            # Expected format: path <TAB> dimensions <TAB> polygons
            # Dimensions/Polygons format: python literal (e.g. tuples, lists)
            parts = line.split('\t')
            path, dims, polys = None, None, None
            
            if len(parts) == 3:
                path = parts[0].strip()
                try:
                    dims = ast.literal_eval(parts[1].strip())
                    polys = ast.literal_eval(parts[2].strip())
                except Exception:
                    path = None # Parsing failed

            if path is None:
                bad_lines += 1
                if bad_lines <= 10:
                    print(f"Warning: skipping malformed line {lineno}", file=sys.stderr)
                continue

            orig_basename = os.path.basename(path)
            
            # Create a completely new, clash-proof filename
            ext = os.path.splitext(orig_basename)[1]
            new_basename = f"{current_id}{ext}"
            
            # Match labels to polygons closely
            text = gt_dict.get(path, "")
            if len(polys) == 1:
                labels = [text]
            else:
                words = text.split()
                if len(words) == len(polys):
                    labels = words
                else:
                    labels = words[:len(polys)]
                    while len(labels) < len(polys):
                        labels.append("...")
            
            # Store parsed data
            temp_data[new_basename] = {
                'orig_path': path,
                'orig_basename': orig_basename,
                'dims': dims,
                'polygons': polys,
                'labels': labels
            }
            current_id += 1

    new_basenames = list(temp_data.keys())
    
    if seed is not None:
        rnd = random.Random(seed)
        rnd.shuffle(new_basenames)
    else:
        random.shuffle(new_basenames)

    n_total = len(new_basenames)
    split_idx = int(n_total * split)
    
    new_train_basenames = new_basenames[:split_idx]
    new_val_basenames = new_basenames[split_idx:]

    # Worker function to process a list of files
    def process_split(basename_list: list, dest_dir: str) -> Tuple[Dict, int, int]:
        images_dir = os.path.join(dest_dir, 'images')
        os.makedirs(images_dir, exist_ok=True)
        
        # Prepare tasks for multiprocessing
        tasks = []
        for new_basename in basename_list:
            entry = temp_data[new_basename]
            orig_path = entry['orig_path']
            orig_basename = entry['orig_basename']
            tasks.append((orig_path, orig_basename, new_basename, input_dir, images_dir))
            
        labels_map = {}
        moved_count = 0
        missing_count = 0
        
        if not tasks:
            return labels_map, moved_count, missing_count

        procs = max(1, min(len(tasks), cpu_count() - 1 or 1))
        
        with Pool(processes=procs) as pool:
            for res_basename, ok, file_hash, msg in pool.imap_unordered(resolve_hash_and_move, tasks):
                if file_hash:
                    # Construct final JSON entry
                    entry = temp_data[res_basename]
                    labels_map[res_basename] = {
                        'img_dimensions': entry['dims'],
                        'img_hash': file_hash,
                        'polygons': entry['polygons'],
                        'labels': entry['labels']
                    }
                
                if ok:
                    moved_count += 1
                else:
                    # If hash exists, we successfully processed it but maybe couldn't move (e.g. exists)
                    if not file_hash:
                        missing_count += 1
                        print(f"Warning: {res_basename}: {msg}", file=sys.stderr)
        
        return labels_map, moved_count, missing_count

    print(f"Processing Train Data ({len(new_train_basenames)} items)...")
    new_train_labels, m_train, miss_train = process_split(new_train_basenames, train_dir)
    
    print(f"Processing Val Data ({len(new_val_basenames)} items)...")
    new_val_labels, m_val, miss_val = process_split(new_val_basenames, val_dir)

    # 6. Merge with Existing JSONs and Save
    existing_train_map.update(new_train_labels)
    with open(train_json_path, 'w', encoding='utf-8') as out:
        json.dump(existing_train_map, out, ensure_ascii=False, indent=4)
    
    existing_val_map.update(existing_val_map) # This looks like a mistake in logic if not merging.
    # Correct merge:
    existing_val_map.update(new_val_labels)
    with open(val_json_path, 'w', encoding='utf-8') as out:
        json.dump(existing_val_map, out, ensure_ascii=False, indent=4)

    print("-" * 40)
    print(f"Wrote {len(existing_train_map)} total entries to {train_json_path}")
    print(f"Wrote {len(existing_val_map)} total entries to {val_json_path}")
    print(f"Total lines processed: {total}, Bad lines: {bad_lines}")
    print(f"New train images: {m_train}, Missing/Failed: {miss_train}")
    print(f"New val images:   {m_val}, Missing/Failed: {miss_val}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert polygon GT file to JSON mapping and merge safely by renaming images.')
    parser.add_argument('input', nargs='?', default='detect/', help='Input directory containing coords.txt and gt.txt (default: detect/)')
    parser.add_argument('outdir', nargs='?', default='results', help='Output base directory (default: results)')
    parser.add_argument('--split', type=float, default=0.75, help='Train split proportion (default: 0.75)')
    parser.add_argument('--seed', type=int, default=42, help='Shuffle seed (default: 42). Use -1 to disable.')
    parser.add_argument('--start-id', type=int, default=-1, help='ID to start renaming from. Defaults to auto-detect highest existing ID.')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input directory not found: {args.input}", file=sys.stderr)
        sys.exit(2)
        
    seed = None if args.seed == -1 else args.seed
    convert(args.input, args.outdir, split=args.split, seed=seed, start_id=args.start_id)
