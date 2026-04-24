#!/usr/bin/env python3
"""Convert a ground-truth file to JSON mapping filename -> text and merge safely.

Usage:
    python3 tools/gt_to_json_merge.py results/gt.txt results --start-id 100

Behavior:
- Reads existing JSON files in destination to avoid data loss.
- Renames incoming images sequentially based on a starting ID to PREVENT CLASHES.
- If --start-id is not provided, it auto-detects the highest existing numeric ID.
- Splits the new dataset and merges the JSON dictionaries.
- Moves and renames files to results/train/images/ and results/val/images/.
"""
import argparse
import json
import os
import sys
import re
import random
import shutil
from multiprocessing import Pool, cpu_count
from typing import Optional, Tuple, Dict

# helper used by worker processes
def resolve_and_move(task: Tuple[str, str, str, str, str]) -> Tuple[str, bool, str]:
    """
    task: (orig_path, orig_basename, new_basename, input_dir, dest_images_dir)
    returns: (new_basename, moved_bool, message)
    """
    orig_path, orig_basename, new_basename, input_dir, dest_images_dir = task
    
    def find_source(orig_path_local: str, basename_local: str, input_dir_local: str) -> Optional[str]:
        if os.path.isabs(orig_path_local):
            if os.path.exists(orig_path_local):
                return orig_path_local
        else:
            cand = os.path.join(input_dir_local, orig_path_local)
            if os.path.exists(cand):
                return cand
            cand = os.path.join(os.getcwd(), orig_path_local)
            if os.path.exists(cand):
                return cand
            for root, _, files in os.walk(input_dir_local):
                if basename_local in files:
                    return os.path.join(root, basename_local)
        return None

    try:
        src = find_source(orig_path, orig_basename, input_dir)
        if not src:
            return (new_basename, False, f"source not found (orig: {orig_path})")
        
        dst = os.path.join(dest_images_dir, new_basename)
        os.makedirs(dest_images_dir, exist_ok=True)
        
        if os.path.exists(dst):
            return (new_basename, False, f"destination exists (clash!): {dst}")
        
        shutil.move(src, dst)
        return (new_basename, True, f"moved and renamed {src} -> {dst}")
    except Exception as e:
        return (new_basename, False, f"error moving: {e}")

def load_json_if_exists(path: str) -> Dict[str, str]:
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

def convert(infile: str, outdir: str, split: float = 0.7, seed: int | None = 42, start_id: int | None = None):
    input_dir = os.path.dirname(os.path.abspath(infile)) or os.getcwd()
    
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

    # 4. Parse the NEW input file and rename on the fly
    new_mapping = {}          # new_basename -> text
    mapping_tasks = {}        # new_basename -> (orig_path, orig_basename)
    
    total = 0
    bad_lines = 0
    split_re = re.compile(r"\s+")

    with open(infile, 'r', encoding='utf-8') as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.rstrip('\n')
            if not line:
                continue
            total += 1
            parts = split_re.split(line, maxsplit=1)
            if len(parts) < 2:
                bad_lines += 1
                continue
            
            orig_path, text = parts[0], parts[1].strip()
            orig_basename = os.path.basename(orig_path)
            
            # Create a completely new, clash-proof filename
            ext = os.path.splitext(orig_basename)[1]
            new_basename = f"{current_id}{ext}"
            
            new_mapping[new_basename] = text
            mapping_tasks[new_basename] = (orig_path, orig_basename)
            
            current_id += 1 # Increment for the next image

    # 5. Shuffle and Split the NEW data
    items = list(new_mapping.items())
    if seed is not None:
        rnd = random.Random(seed)
        rnd.shuffle(items)
    else:
        random.shuffle(items)

    n_total = len(items)
    split_idx = int(n_total * split)
    
    new_train_items = dict(items[:split_idx])
    new_val_items = dict(items[split_idx:])

    # 6. Merge with Existing JSONs and Save
    existing_train_map.update(new_train_items)
    with open(train_json_path, 'w', encoding='utf-8') as out:
        json.dump(existing_train_map, out, ensure_ascii=False, indent=4)
    
    existing_val_map.update(new_val_items)
    with open(val_json_path, 'w', encoding='utf-8') as out:
        json.dump(existing_val_map, out, ensure_ascii=False, indent=4)

    # 7. Move and Rename Images
    def move_split_images_parallel(split_map: dict, dest_dir: str) -> Tuple[int, int]:
        images_dir = os.path.join(dest_dir, 'images')
        os.makedirs(images_dir, exist_ok=True)

        tasks = []
        for new_basename in split_map.keys():
            orig_data = mapping_tasks.get(new_basename)
            if orig_data:
                orig_path, orig_basename = orig_data
                tasks.append((orig_path, orig_basename, new_basename, input_dir, images_dir))

        if not tasks:
            return 0, 0

        moved, failed = 0, 0
        procs = max(1, min(len(tasks), cpu_count() - 1 or 1))
        with Pool(processes=procs) as pool:
            for new_base, ok, msg in pool.imap_unordered(resolve_and_move, tasks):
                if ok:
                    moved += 1
                else:
                    failed += 1
                    print(f"Warning: {msg}", file=sys.stderr)
        return moved, failed

    print("--- Moving and Renaming Images ---")
    moved_train, fail_train = move_split_images_parallel(new_train_items, train_dir)
    moved_val, fail_val = move_split_images_parallel(new_val_items, val_dir)

    print(f"Train images added: {moved_train} (Total now: {len(existing_train_map)})")
    print(f"Val images added:   {moved_val} (Total now: {len(existing_val_map)})")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert gt.txt to JSON and merge safely by renaming images.')
    parser.add_argument('input', nargs='?', default='results/gt.txt', help='Input GT file')
    parser.add_argument('outdir', nargs='?', default='results', help='Output base dir')
    parser.add_argument('--split', type=float, default=0.75, help='Proportion of new data to train set')
    parser.add_argument('--seed', type=int, default=42, help='Shuffle seed')
    parser.add_argument('--start-id', type=int, default=-1, help='ID to start renaming from. Defaults to auto-detect highest existing ID.')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Input file not found: {args.input}", file=sys.stderr)
        sys.exit(2)
        
    seed = None if args.seed == -1 else args.seed
    convert(args.input, args.outdir, split=args.split, seed=seed, start_id=args.start_id)