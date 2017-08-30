#!/usr/bin/env python3
import sys
import argparse
from collections import defaultdict
import reuter_util.bgp as bgp


def parse_arguments(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("data", help="bgp data")
    return parser.parse_args(args)


ANCHOR_EXPERIMENT_PAIRS = [('147.28.240.0/24', '147.28.241.0/24'),
                           ('147.28.242.0/24', '147.28.244.0/24'),
                           ('147.28.243.0/24', '147.28.245.0/24'),
                           ('147.28.246.0/24', '147.28.247.0/24'),
                           ('147.28.248.0/24', '147.28.249.0/24'),
                           ('147.28.250.0/24', '147.28.251.0/24'),
                           ('147.28.252.0/24', '147.28.253.0/24'),
                           ('147.28.254.0/24', '147.28.255.0/24')
                           ]
def main(args):
    args = parse_arguments(args)

    for pair in ANCHOR_EXPERIMENT_PAIRS:
        anchor = pair[0]
        experiment = pair[1]
        print("Anchor: {0} ; Experiment: {1}".format(anchor, experiment))

        anchor_paths_counter = defaultdict(int)
        experiment_paths_counter = defaultdict(int)
        anchor_paths = defaultdict(set)
        experiment_paths = defaultdict(set)
        monitors = set()

        with open(args.data, 'r') as f:
            for line in f:
                line = line.split('|')
                if not (line[0] == 'R' and line[1] == 'R'):
                    continue

                prefix = line[7].rstrip()
                as_path = line[9].rstrip()
                peer_ip = line[6].rstrip()
                peer_asn = line[5].rstrip()
                monitor = (peer_asn, peer_ip)
                monitors.add(monitor)
                if prefix == anchor:
                    anchor_paths_counter[monitor] += 1
                    anchor_paths[monitor].add(as_path)
                if prefix == experiment:
                    experiment_paths_counter[monitor] += 1
                    experiment_paths[monitor].add(as_path)

        for monitor in monitors:
            if monitor in anchor_paths and monitor in experiment_paths:
                if anchor_paths[monitor] != experiment_paths[monitor] or \
                                anchor_paths_counter[monitor] != experiment_paths_counter[monitor]:
                    anchor_paths_m = anchor_paths[monitor]
                    print(monitor[0] + '|' + monitor[1] + "|" + str(anchor_paths_m))
        print("========================")


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
