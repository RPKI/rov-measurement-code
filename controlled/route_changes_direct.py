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
                           ('147.28.252.0/24', '147.28.253.0/24')
                           ]


def main(args):
    args = parse_arguments(args)

    for pair in ANCHOR_EXPERIMENT_PAIRS:
        anchor = pair[0]
        experiment = pair[1]
        print("Anchor: {0} ; Experiment: {1}".format(anchor, experiment))

        anchor_direct_paths = defaultdict(int)
        experiment_direct_paths = defaultdict(int)
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
                if len(as_path.split(' ')) == 2:
                    if prefix == anchor:
                        anchor_direct_paths[monitor] += 1
                    if prefix == experiment:
                        experiment_direct_paths[monitor] += 1

        for monitor in monitors:
            if monitor in anchor_direct_paths and monitor in experiment_direct_paths:
                if anchor_direct_paths[monitor] != experiment_direct_paths[monitor]:
                    print(monitor[0] + '|' + monitor[1])
        print("========================")


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
