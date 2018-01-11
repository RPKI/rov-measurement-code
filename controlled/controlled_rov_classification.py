#!/usr/bin/env python3
import yaml
import sys
import argparse
import os
import time
from _pybgpstream import BGPStream, BGPElem, BGPRecord
from datetime import datetime, timedelta
from reuter_util import bgp
from calendar import timegm
from collections import defaultdict
import psycopg2


def timeit(method):

    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()

        print('%r (%r, %r) %2.2f sec' % \
              (method.__name__, args, kw, te-ts))
        return result

    return timed


def init_stream(config_files, start_time, end_time):
    stream = BGPStream()
    rec = BGPRecord()
    stream.add_filter('project', 'ris')
    stream.add_filter('project', 'routeviews')
    stream.add_filter('record-type', 'ribs')
    for exp_id in config_files:
        config_file = config_files[exp_id]
        stream.add_filter('prefix', config_file['superprefix'])
    stream.add_interval_filter(start_time, end_time)
    return stream, rec


def get_bgp_data_from_stream(config_files, start, end):
    all_experiment_prefixes = set()
    for exp_id in config_files:
        config_file = config_files[exp_id]
        all_experiment_prefixes.update(config_file['prefixes'])
    stream, rec = init_stream(config_files, start, end)
    stream.start()

    vp_routes = defaultdict(lambda: defaultdict(dict))
    while stream.get_next_record(rec):
        elem = rec.get_next_elem()
        while elem:
            if elem.type == "R" and elem.fields['prefix'] in all_experiment_prefixes:
                vp = (elem.peer_asn, elem.peer_address)
                timestamp = elem.time
                timestamp = timestamp - (timestamp % 3600)
                as_path = elem.fields['as-path']
                prefix = elem.fields['prefix']
                vp_routes[vp][prefix][timestamp] = as_path
            elem = rec.get_next_elem()
    return vp_routes


def get_bgp_data_from_file(config_files, filename):
    vp_routes = defaultdict(lambda: defaultdict(dict))
    all_experiment_prefixes = set()
    for exp_id in config_files:
        config_file = config_files[exp_id]
        all_experiment_prefixes.update(config_file['prefixes'])

    with open(filename, 'r') as f:
        for line in f:
            if line[:3] == "R|R":
                line = line.split('|')
                peer_asn = int(line[5])
                peer_address = line[6]
                vp = (peer_asn, peer_address)
                prefix = line[7]
                as_path = line[9]
                as_path = bgp.remove_prepending_from_as_path(as_path)
                origin_asn = int(line[10])
                timestamp = int(line[2])
                timestamp = timestamp - (timestamp % 3600)
                collector = line[4]
                project = line[3]

                if prefix in all_experiment_prefixes:
                    vp_routes[vp][prefix][timestamp] =  as_path

    return vp_routes


def read_experiment_config_files(config_file_dir):
    config_files = {}
    config_filenames = os.listdir(config_file_dir)
    for config_file in config_filenames:
        if config_file.endswith('.yaml'):
            fd = open(config_file_dir + '/' + config_file, 'r')
            config_file = yaml.load(fd)
            config_files[config_file['experiment_id']] = config_file
            fd.close()
    return config_files


def parse_arguments(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_configs", help="Directory with YAML experiment config files")
    parser.add_argument("day", help="Day to analyse data from. Format %Y-%m-%d")
    return parser.parse_args(args)


def get_expected_rpki_status(prefix, origin_asn, timestamp, config, day):
    # Check ROAs
    roas = config['roas'][prefix]
    prop_time = 0

    #
    # If start <= timestamp < end & asn == origin_asn then VALID
    for roa in roas:

        str_start = roa['period']['start']
        str_end = roa['period']['end']
        start = datetime.strptime(day + ' ' + str_start, "%Y-%m-%d %H:%M %Z")
        end = datetime.strptime(day + ' ' + str_end, "%Y-%m-%d %H:%M %Z")

        u_start = timegm(start.utctimetuple())
        u_end = timegm(end.utctimetuple())

        roa_is_active = False
        if u_start < u_end:
            if u_start + prop_time < timestamp and timestamp <= u_end + prop_time:
                roa_is_active = True

        else:
            if u_start + prop_time < timestamp or timestamp <= u_end + prop_time:
                roa_is_active = True

        if roa['asn'] == origin_asn and roa_is_active:
            return 'VALID'

    if roas:
        return 'INVALID'
    return 'UNKNOWN'


def analyze_experiment5(config, vp_routes, day):
    for vp in vp_routes:
        vp_asn = vp[0]
        direct_route = str(vp_asn) + ' 47065'
        for prefix_pair in config['prefix_pairs']:
            p_a = prefix_pair['anchor']
            p_e = prefix_pair['experiment']
            routes = vp_routes[vp]
            if p_a not in routes:
                continue

            # If VP has constant, direct, route to p_a..
            if all(vp_routes[vp][p_a][timestamp] == direct_route for timestamp in vp_routes[vp][p_a]):

                if not all(vp_routes[vp][p_e][timestamp] == direct_route for timestamp in vp_routes[vp][p_e]):
                    print('==============================================')
                    print("VP {0}|{1} filtering for Anchor {1} and Experiment Prefix {2}:".format(vp[0],vp[1], p_a, p_e))
                    print("P_a routes:".format())
                    sorted_ts = sorted(vp_routes[vp][p_a])
                    for ts in sorted_ts:
                        print('\tTime: {0}; AS_PATH: {1}'.format(datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S'), vp_routes[vp][p_a][ts]))
                    print('----')
                    print("P_e routes:".format())
                    sorted_ts = sorted(vp_routes[vp][p_e])
                    for ts in sorted_ts:
                        print('\tTime: {0}; AS_PATH: {1}'.format(datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S'), vp_routes[vp][p_e][ts]))

                if not vp_routes[vp][p_e]:
                    pass


def add_missing_routes(config_files, vp_routes, day):
    for vp in vp_routes:
        for exp_id in config_files:
            config = config_files[exp_id]
            for prefix_pair in config['prefix_pairs']:
                p_a = prefix_pair['anchor']
                p_e = prefix_pair['experiment']

                for timestamp in vp_routes[vp][p_a]:
                    if timestamp not in vp_routes[vp][p_e]:
                        vp_routes[vp][p_e][timestamp] = 'missing'


def main(args):
    args = parse_arguments(args)
    config_files = read_experiment_config_files(args.experiment_configs)
    start = timegm(datetime.strptime(args.day + " 00:00:00 UTC", "%Y-%m-%d %H:%M:%S %Z").utctimetuple())
    end = timegm(datetime.strptime(args.day + " 23:59:59 UTC", "%Y-%m-%d %H:%M:%S %Z").utctimetuple())

    vp_routes = get_bgp_data_from_file(config_files, 'data/2018-01-01-exp5.ribs')
    add_missing_routes(config_files, vp_routes, args.day)

    analyze_experiment5(config_files[5], vp_routes, args.day)




if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))


# 1. Get BGP data for a whole day ( For now, just use files but also do bgpstream code)
# 2. For each VP, store all routes for each prefixes
# 2.1 We have data for a whole day, so lots of dumps per VP possibly. Store them all in a list. so:

# VP -> Prefix -> [ route_t1, route_t2, route_t3] etc.

# 3. Now find VP that have constant, direct route to an anchor
# 4. Check if they have a direct route to the corresponding experiment prefixes, and if that direct route changes
# with time (either is gone, or indirect)