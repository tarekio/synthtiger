"""
SynthTIGER
Copyright (c) 2021-present NAVER Corp.
MIT license
"""
import os
import argparse
import pprint
import time

import synthtiger


def run(args):
    if args.config is not None:
        config = synthtiger.read_config(args.config)

    pprint.pprint(config)

    synthtiger.set_global_random_seed(args.seed)
    template = synthtiger.read_template(args.script, args.name, config)
    generator = synthtiger.generator(
        args.script,
        args.name,
        config=config,
        count=args.count,
        worker=args.worker,
        seed=args.seed,
        retry=True,
        verbose=args.verbose,
    )

    existing_lines = 0

    if args.output is not None:

        gt_file = os.path.join(args.output, "gt.txt")
        if os.path.exists(gt_file):
            print(f"{gt_file} already exists. Checking length to avoid overwriting.")
            
            with open(gt_file, 'r', encoding='utf-8') as f:
                existing_lines = sum(1 for _ in f)
            print(f"{existing_lines} existing lines found. New data will start from index {existing_lines}.")
            template.init_save(args.output, mode="a")
        else:
            template.init_save(args.output)

    for idx, (task_idx, data) in enumerate(generator):
        if args.output is not None:
            task_idx = task_idx + existing_lines
            template.save(args.output, data, task_idx)
        print(f"Generated {idx + 1} data (file {task_idx})")

    if args.output is not None:
        template.end_save(args.output)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o",
        "--output",
        metavar="DIR",
        type=str,
        help="Directory path to save data.",
    )
    parser.add_argument(
        "-c",
        "--count",
        metavar="NUM",
        type=int,
        default=100,
        help="Number of output data. [default: 100]",
    )
    parser.add_argument(
        "-w",
        "--worker",
        metavar="NUM",
        type=int,
        default=0,
        help="Number of workers. If 0, It generates data in the main process. [default: 0]",
    )
    parser.add_argument(
        "-s",
        "--seed",
        metavar="NUM",
        type=int,
        default=None,
        help="Random seed. [default: None]",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Print error messages while generating data.",
    )
    parser.add_argument(
        "script",
        metavar="SCRIPT",
        type=str,
        help="Script file path.",
    )
    parser.add_argument(
        "name",
        metavar="NAME",
        type=str,
        help="Template class name.",
    )
    parser.add_argument(
        "config",
        metavar="CONFIG",
        type=str,
        nargs="?",
        help="Config file path.",
    )
    args = parser.parse_args()

    pprint.pprint(vars(args))

    return args


def main():
    start_time = time.time()
    args = parse_args()
    run(args)
    end_time = time.time()
    print(f"{end_time - start_time:.2f} seconds elapsed")


if __name__ == "__main__":
    main()
