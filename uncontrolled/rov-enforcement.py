#!/usr/bin/env python3
import sys
import argparse
import csv
from collections import defaultdict
import reuter_util.general as gen
import reuter_util.bgp as bgp
import time
import random


def timeit(method):

    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()

        print('%r (%r, %r) %2.2f sec' % \
              (method.__name__, args, kw, te-ts))
        return result

    return timed


def parse_arguments(args):
    parser = argparse.ArgumentParser()

    parser.add_argument("path_diversity", help="Path diversity is a file that tells us which AS is originating how "+
                                               "many routes that are seen by a vantage point. See path-diversity.py")

    parser.add_argument("as_relationship", help="CAIDAs AS relationship file. Filename format is as_rel_<date>.txt")
    parser.add_argument("data", help="BGP RIB Data. Must be the same data as was used for generation of path_diversity")
    parser.add_argument("random_sets", type=int, help="Number of random sets of vantage points to run with")
    return parser.parse_args(args)


def find_multiple_origin_enforcers(global_rov_enforcers_map, local_rov_enforcers_map):
    # Each divergent AS with at least 3 origins is flagged as ROV enforcing
    global_rov_enforcers = set()
    for div_as in global_rov_enforcers_map:
        if len(global_rov_enforcers_map[div_as]) >= 3:
            global_rov_enforcers.add(div_as)

    local_rov_enforcers = defaultdict(set)
    for monitor in local_rov_enforcers_map:
        for div_as in local_rov_enforcers_map[monitor]:
            if len(local_rov_enforcers_map[monitor][div_as]) >= 3:
                local_rov_enforcers[monitor].add(div_as)
    return global_rov_enforcers, local_rov_enforcers


def write_rov_enforcers_to_file(global_rov_enforcers, local_rov_enforcers):
    gen.make_dirs('results')
    with open('results/global_rov_enforcers.txt', 'w') as f:
        for rov_enforcer in global_rov_enforcers:
            f.write(rov_enforcer + '\n')

    with open('results/local_rov_enforcers.txt', 'w') as f:
        for monitor in local_rov_enforcers:
            line = monitor[0] + ',' + monitor[1]
            for rov_enforcer in local_rov_enforcers[monitor]:
                line += ' ' + rov_enforcer
            line += '\n'
            f.write(line)


def write_analysis_results_to_file(vp_set, non_rov, rov_cand, rov_enf, false_rov_cand, false_rov_enf, filename, mode):
    with open(filename, mode) as f:
        f.write("{0}|{1}|{2}|{3}|{4}|{5}\n".format(len(vp_set), len(non_rov), len(rov_cand), len(rov_enf),
                                                   len(false_rov_cand), len(false_rov_enf)))


def find_rov_enforcing_as(rov_candidate_set):
    """
    Any AS that has been marked as a ROV candidate for at least three different origin AS, is classified as ROV
    enforcing.
    :param rov_candidate_set: Dictionary rov_candiate->set(originAS)
    :return: set of ROV enforcing AS
    """
    rov_enforcing = set()
    for rov_candidate in rov_candidate_set:
        if len(rov_candidate_set[rov_candidate]) >= 3:
            rov_enforcing.add(rov_candidate)
            print("ROV enforcer: {0}".format(rov_candidate))
            print("Origins: {0}".format(rov_candidate_set[rov_candidate]))
    return rov_enforcing


def find_rov_candidates(vantage_point_set, special_origin_paths, non_rov_enforcing):
    """
    :param vantage_point_set: Set of vantage points for which to find ROV candidates
    :param special_origin_paths: Dictionary with paths to special origins.
    vantage_point->origin->{set(invalid_paths), set(non_invalid_paths)}
    :param non_rov_enforcing: Dictionary with vantage_point->set(non-ROV enforcing AS)
    :return: For each vantage point, for each origin, set of AS that possibly enforce ROV on the origins prefixes
    :return: All 'non_rov_enforcing' AS observed by the monitors in monitor_set
    """

    # First join all non_rov_enforcing sets
    total_non_rov_enforcing = set()
    for vantage_point in vantage_point_set:
        total_non_rov_enforcing = total_non_rov_enforcing.union(non_rov_enforcing[vantage_point])

    # Then go through all paths, for each origin find ROV candidates. Store in Dictionary: rov_candidate_AS->set(origin)
    rov_candidate_set = defaultdict(set)
    for vantage_point in vantage_point_set:
        for origin in special_origin_paths[vantage_point]:
            non_invalid_paths = special_origin_paths[vantage_point][origin]['non_invalid']

            # Compare each invalid path to each non-invalid path
            for invalid_path in special_origin_paths[vantage_point][origin]['invalid']:
                for non_invalid_path in non_invalid_paths:

                    # If they are the same, we can't flag any AS
                    if invalid_path == non_invalid_path:
                        continue

                    # Get all AS that are different. Then discard those who are non-ROV enforcing.
                    # If there is exactly one AS left, then tag it as ROV candidate
                    inv_tmp = invalid_path.split(' ')
                    inv_tmp.reverse()
                    non_inv_tmp = non_invalid_path.split(' ')
                    non_inv_tmp.reverse()
                    if inv_tmp[0] != non_inv_tmp[0]:
                        print("ERROR: Paths don't have same origin!`")
                        sys.exit()

                    possible_rov_cand = set(non_inv_tmp).difference(set(inv_tmp))
                    possible_rov_cand = possible_rov_cand.difference(total_non_rov_enforcing)
                    if len(possible_rov_cand) == 1:
                        rov_candidate_set[possible_rov_cand.pop()].add(origin)

    return rov_candidate_set, total_non_rov_enforcing


def do_analysis_for_vantage_point_set(vantage_point_set, special_origin_path_sets, non_rov_enforcing_sets):
    """
    Flags AS as 'non ROV enforcing', 'ROV enforcing candidate', and 'ROV enforcing'. Only considers AS from paths
    that were observed by vantage points in vantage_point_set
    :param vantage_point_set: set of vantage_point
    :param special_origin_path_sets: Dictionary vantage_point->origin->{set(invalid_paths}, set(non_invalid_paths)}
    :param non_rov_enforcing_sets: Dictionary vantage_point->set(non-ROV enforcing AS)
    :return: non_rov_enforcing: set of 'non ROV enforcing' AS as seen by vantage point in vantage_point_set
    :return: rov_candidates: set of AS that are candidates for ROV enforcement (i.e. flagged by at least 1 origin)
    :return: rov_enforcing: set of AS that are flagged as 'ROV enforcing' (i.e. flagged by at least 3 origins)
    """

    rov_candidates_dict, non_rov_enforcing = find_rov_candidates(vantage_point_set, special_origin_path_sets,
                                                                 non_rov_enforcing_sets)

    rov_enforcing = find_rov_enforcing_as(rov_candidates_dict)
    rov_candidates = set(rov_candidates_dict.keys())

    return non_rov_enforcing, rov_candidates, rov_enforcing


@timeit
def read_bgp_paths(data_file, special_origins, p2c_data):
    """
    For each vp, store all paths to special origins (separated by non_invalid, invalid). Also for each vp
    store all AS seen on invalid paths (except when origin is vp or customer of vp).
    :param data_file: BGP RIB file
    :param p2c_data: Dictionary providerAS->set(customerAS)
    :param special_origins: Dictionary vantage_point->set(special_origins)
    :return: special_origin_paths: Dictionary, vantage_point->origin->{set(invalid_paths), set(non_invalid_paths)}
    :return: non_rov_enforcing: Dictionary, vantage_point->set(non-ROV enforcing AS)
    """
    non_rov_enforcing = defaultdict(set)
    special_origin_paths = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    with open(data_file, 'r') as f:
        for line in f:
            if not bgp.is_relevant_line(line, ['\n', '/']):
                continue
            bgp_fields = bgp.get_bgp_fields(line)
            if not bgp.is_valid_bgp_entry(bgp_fields):
                continue

            vantage_point = (bgp_fields['peer_ip'], bgp_fields['peer_asn'])
            origin = bgp_fields['origin']

            # Exclude announcements where vantage_point is origin or a customer of vantage_point is origin
            if origin == vantage_point[1] or origin in p2c_data[vantage_point[1]]:
                continue

            vstate = bgp_fields['vstate']
            as_path = bgp.remove_prepending_from_as_path(bgp_fields['as_path'])

            if vstate > 2:
                # If invalid, add all AS on path except origin to 'non-ROV enforcing'
                for asn in as_path.split(' ')[:-1]:
                    non_rov_enforcing[vantage_point].add(asn.rstrip())

            # If its a special origin, store its path
            if origin in special_origins[vantage_point]:
                if vstate > 2:
                    special_origin_paths[vantage_point][origin]['invalid'].add(as_path)
                else:
                    special_origin_paths[vantage_point][origin]['non_invalid'].add(as_path)
    return special_origin_paths, non_rov_enforcing


def read_as_relationships(filename):
    """
    Format of file is:
    <AS1>|<AS2>|<relationship>
    where relationship is -1 for p2c, 0 for p2p
    :param filename:
    :return: Dictionary with providerAS->set(customerAS)
    """
    p2c_data = defaultdict(set)
    with open(filename, 'r') as f:
        for line in f:
            if line[0] == "#":
                continue
            line = line.split('|')
            as1 = line[0]
            as2 = line[1]
            rel = int(line[2])
            if rel == -1:
                p2c_data[as1].add(as2)
    return p2c_data


@timeit
def read_path_diversity(filename):
    """
    Format of file is:
    vpIP,vpAS,origin,#dist_paths,#dist_ni_paths,#dist_i_paths,#dist_i_len_paths,#dist_i_as_paths,#dist_i_as_len_paths
    :param filename:
    :return: special_origins: Dictionary with vantage_point->set(originAS) where origin AS have at least one non-invalid
                              one invalid prefix announced
    :return: all_vantage_points: Set of all vantage points
    """
    special_origins = defaultdict(set)
    all_vantage_points = set()
    with open(filename, 'r') as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        next(reader, None)
        for row in reader:
            vp_ip = row[0]
            vp_asn = row[1]
            vantage_point = (vp_ip, vp_asn)
            all_vantage_points.add(vantage_point)
            origin = row[2]
            dist_ni_paths = int(row[4])
            dist_i_paths = int(row[5])
            if dist_i_paths > 0 and dist_ni_paths > 0:
                special_origins[vantage_point].add(origin)
    return special_origins, all_vantage_points


def main(args):
    gen.make_dirs('results')
    results_file = 'results/analysis_results.txt'
    args = parse_arguments(args)

    # Special origins are origin AS that originate at least a non-invalid and an invalid prefix seen by a vantage point
    special_origins, all_vantage_points = read_path_diversity(args.path_diversity)

    # We want to exclude invalid announcements that originate from a vantage point AS or a customer of one, so we need
    # AS relationship data.
    p2c_data = read_as_relationships(args.as_relationship)

    # For each vantage point, store 1) All paths to a special origin 2) all AS found on invalid paths to the vantage
    # point (except when vp or customer of vp is origin).
    # non_rov_enforcing is the AS that have been found on _any_ invalid path, grouped by vantage point
    special_origin_paths, non_rov_enforcing = read_bgp_paths(args.data, special_origins, p2c_data)

    # ------------------ Start of analysis -------------------
    # All vantage points
    non_rov, rov_cand, rov_enf = do_analysis_for_vantage_point_set(all_vantage_points, special_origin_paths,
                                                                   non_rov_enforcing)
    write_analysis_results_to_file(all_vantage_points, non_rov, rov_cand, rov_enf, set(), set(), results_file, 'a')

    # ------------------  Analysis of vantage point groups ---
    # Global set of non-ROV enforcing AS, regardless of which vp saw it
    global_non_rov_enforcing = set()
    for vantage_point in non_rov_enforcing:
        global_non_rov_enforcing = global_non_rov_enforcing.union(non_rov_enforcing[vantage_point])

    set_sample_sizes = [10, 20, 44, 60, 80, 100, 200, 300, 400, 500, 600, 700, 800, 900]
    for sample_size in set_sample_sizes:
        known_sets = set()
        for i in range(0, args.random_sets):
            # Pick random vantage points
            random_vp_set = frozenset(random.sample(all_vantage_points, sample_size))
            while random_vp_set in known_sets:
                random_vp_set = frozenset(random.sample(all_vantage_points, sample_size))

            known_sets.add(random_vp_set)
            # Do analysis only with data from these vps
            non_rov, rov_cand, rov_enf = do_analysis_for_vantage_point_set(random_vp_set, special_origin_paths,
                                                             non_rov_enforcing)

            # See how many of the ROV candidates and ROV enforcers are actually seen as non-ROV on a global scale
            false_rov_cand = rov_cand.intersection(global_non_rov_enforcing)
            false_rov_enf = rov_enf.intersection(global_non_rov_enforcing)

            write_analysis_results_to_file(random_vp_set, non_rov, rov_cand, rov_enf, false_rov_cand, false_rov_enf
                                           , results_file, 'a')

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
