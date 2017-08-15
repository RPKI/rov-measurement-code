#!/usr/bin/env python3
import sys
import argparse
import csv
import reuter_util.bgp as bgp
import reuter_util.general as gen


def parse_arguments(args):
    parser = argparse.ArgumentParser()
    # format is: <dump-type>|<elem-type>|<record-ts>|<project>|<collector>|<peer-ASn>|<peer-IP>|
    # <prefix>|<next-hop-IP>|<AS-path>|<origin-AS>|<communities>|<old-state>|<new-state>|<validity-state>
    parser.add_argument("data", help="BGP RIB dump")
    args = parser.parse_args(args)
    return args


def get_invalid_paths(origin_p):
    """
    :param origin_p:
    :return: Union of the 3 invalid path sets
    """
    invalid_len = origin_p['invalid_len_paths']
    invalid_as = origin_p['invalid_as_paths']
    invalid_as_and_len = origin_p['invalid_as_and_len_paths']
    return invalid_len.union(invalid_as.union(invalid_as_and_len))


def write_path_diversities_to_file(path_diversities, filename):
    with open(filename, 'w') as csv_file:
        datawriter = csv.writer(csv_file)
        headers = ['monitorIP', 'monitorAS', 'origin', '#dist_paths', '#dist_ni_paths', '#dist_i_paths',
                   '#dist_i_len_paths', '#dist_i_as_paths', '#dist_i_as_len_paths']

        datawriter.writerow(headers)
        for monitor in path_diversities:
            for origin in path_diversities[monitor]:
                origin_pd = path_diversities[monitor][origin]
                row = []
                row.append(monitor[0])
                row.append(monitor[1])
                row.append(origin)
                row.append(origin_pd['all'])
                row.append(origin_pd['non_invalid'])
                row.append(origin_pd['invalid'])
                row.append(origin_pd['invalid_len'])
                row.append(origin_pd['invalid_as'])
                row.append(origin_pd['invalid_as_and_len'])
                datawriter.writerow(row)


def gather_paths(filename):
    print("Gathering paths from data")
    paths = {}
    with open(filename, 'r') as f:
        for line in f:
            if not bgp.is_relevant_line(line, ['\n', '/']):
                continue
            bgp_fields = bgp.get_bgp_fields(line)
            if not bgp.is_valid_bgp_entry(bgp_fields):
                continue

            monitor = (bgp_fields['peer_ip'], bgp_fields['peer_asn'])
            as_path = bgp.remove_prepending_from_as_path(bgp_fields['as_path'])
            vstate = bgp_fields['vstate']

            gen.init_dic_with(paths, monitor, {})
            origin_p = gen.init_dic_with(paths[monitor], bgp_fields['origin'],
                                     {'non_invalid_paths': set(), 'invalid_len_paths': set(),
                                      'invalid_as_paths': set(),
                                      'invalid_as_and_len_paths': set()})
            if vstate < 2:
                origin_p['non_invalid_paths'].add(as_path)
            elif vstate == 3:
                origin_p['invalid_as_paths'].add(as_path)
            elif vstate == 4:
                origin_p['invalid_len_paths'].add(as_path)
            elif vstate == 5:
                origin_p['invalid_as_and_len_paths'].add(as_path)
            else:
                if vstate == 2:
                    print("Found RIB entry with validity state 2. Please annotate data with more specific reasons(3-5)")
                else:
                    print("Found unrecognized recognized validity state '{0}'. Exiting".format(vstate))
                sys.exit(-1)

    print("Done reading")
    return paths


def get_path_diversities(paths):
    """
    Find paths diversities for each vantage point (monitor), and origin AS observed from that point.
    Path diversity is the number of distinct AS paths observed from an origin to a vantage point
    :param paths: Dictionary with monitor->origin->(non_)invalid_(len_/as_/as_and_len_)paths
    :return: Nested dictionaries. Top level keys are monitors, 2nd level origins, 3rd level are 'non_invalid',
    'invalid', 'invalid_len', 'invalid_as', 'invalid_as_and_len'.  Values for those are the numbers of distinct AS paths
    observed from monitor to origin with the given validity state. Example:
    (1.9.2.4,1234) -> 8123 -> non_invalid -> 5
    (1.9.2.4,1234) -> 8123 -> invalid* -> 0

    """
    for monitor in paths:
        for origin in paths[monitor]:
            origin_p = paths[monitor][origin]

            origin_p['non_invalid'] = len(origin_p['non_invalid_paths'])
            origin_p['invalid_len'] = len(origin_p['invalid_len_paths'])
            origin_p['invalid_as'] = len(origin_p['invalid_as_paths'])
            origin_p['invalid_as_and_len'] = len(origin_p['invalid_as_and_len_paths'])

            invalid_paths = get_invalid_paths(origin_p)
            all_paths = origin_p['non_invalid_paths'].union(invalid_paths)
            origin_p['invalid'] = len(invalid_paths)
            origin_p['all'] = len(all_paths)
            del all_paths
            del invalid_paths
            del origin_p['non_invalid_paths']
            del origin_p['invalid_len_paths']
            del origin_p['invalid_as_paths']
            del origin_p['invalid_as_and_len_paths']

    return paths


def main(args):
    args = parse_arguments(args)
    paths = gather_paths(args.data)
    path_diversities = get_path_diversities(paths)
    write_path_diversities_to_file(path_diversities, 'path_diversity.csv')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
