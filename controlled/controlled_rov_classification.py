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
import json
import psycopg2


def timeit(method):
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()

        print('%r (%r, %r) %2.2f sec' % \
              (method.__name__, args, kw, te - ts))
        return result

    return timed


def parse_arguments(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_configs", help="Directory with YAML experiment config files")
    parser.add_argument("day", help="Day to analyse data from. Format %Y-%m-%d")
    parser.add_argument("db_config", help="db_config.json")
    return parser.parse_args(args)


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
    raw_data = []
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
                path_len = len(as_path.split(' '))
                origin_asn = int(line[10])
                communities = line[11]
                timestamp = int(line[2])
                timestamp = timestamp - (timestamp % 3600)
                day = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
                collector = line[4]
                project = line[3]

                if communities == "":
                    communities = 'NULL'

                if prefix in all_experiment_prefixes:
                    vp_routes[vp][prefix][timestamp] = as_path
                    raw_data.append((day, timestamp, project, collector, peer_asn, peer_address, prefix,
                                     as_path, path_len, origin_asn, communities))

    return raw_data, vp_routes


def get_expected_rpki_status(prefix, origin_asn, timestamp, config, day):
    roas = config['roas'][prefix]
    prop_time = 0
    for roa in roas:

        str_start = roa['period']['start']
        str_end = roa['period']['end']
        start = datetime.strptime(day + ' ' + str_start, "%Y-%m-%d %H:%M %Z")
        end = datetime.strptime(day + ' ' + str_end, "%Y-%m-%d %H:%M %Z")

        u_start = timegm(start.utctimetuple())
        u_end = timegm(end.utctimetuple())

        roa_is_active = False
        if u_start < u_end:
            if u_start + prop_time < timestamp <= u_end + prop_time:
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
    case1_results = []
    for vp in vp_routes:
        vp_asn = vp[0]
        vp_ip = vp[1]
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
                    # CASE 1: VP has constant, direct route to P_a, but not to P_e
                    case1_result = (day, vp_asn, vp_ip, p_a, p_e)
                    case1_results.append(case1_result)

    return case1_results


def read_vps_from_file(filename):
    vps = set()
    with open(filename, 'r') as f:
        for line in f:
            line = line.split('|')
            vp = (int(line[0].rstrip()), line[1].rstrip())
            vps.add(vp)
    return vps


def insert_analysis_results_to_db(dbname, dbuser, dbpw, dbhost, tablename, data):
    try:
        connect_str = "dbname='{0}' user='{1}' host='{2}' password='{3}'".format(dbname, dbuser, dbhost, dbpw)
        conn = psycopg2.connect(connect_str)
        cursor = conn.cursor()

        for d in data:
            args = "('{0}', {1}, '{2}', '{3}', '{4}')".format(d[0], d[1], d[2], d[3], d[4])
            insert_statement = """INSERT INTO {0} VALUES """.format(tablename)
            cursor.execute(insert_statement + args)
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("ERROR: Can't connect to DB.")
        print(e)
        exit()


def insert_raw_data_to_db(dbname, dbuser, dbpw, dbhost, raw_data):
    try:
        connect_str = "dbname='{0}' user='{1}' host='{2}' password='{3}'".format(dbname, dbuser, dbhost, dbpw)
        conn = psycopg2.connect(connect_str)
        cursor = conn.cursor()

        for rd in raw_data:
            if rd[10] != 'NULL':
                comm = "'{0}'".format(rd[10])
            else:
                comm = rd[9]
            args = "('{0}', {1}, '{2}', '{3}', {4}, '{5}', '{6}', '{7}', {8}, {9}, {10})".format(rd[0], rd[1], rd[2],
                                                                                                 rd[3], rd[4], rd[5],
                                                                                                 rd[6], rd[7], rd[8],
                                                                                                 rd[9], comm)
            cursor.execute("""INSERT INTO raw_data VALUES """ + args)
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("ERROR: Can't connect to DB.")
        print(e)
        exit()


def update_exp5_stats(dbname, dbuser, dbpw, dbhost, case1_results):
    try:
        connect_str = "dbname='{0}' user='{1}' host='{2}' password='{3}'".format(dbname, dbuser, dbhost, dbpw)
        conn = psycopg2.connect(connect_str)
        cursor = conn.cursor()

        vps = [(r[1], r[2]) for r in case1_results]
        for vp in vps:
            sql_data_dates = "SELECT DISTINCT day FROM raw_data WHERE (vp_asn="+str(vp[0])+" AND vp_ip='"+vp[1]+"')"
            cursor.execute(sql_data_dates)
            data_dates = set(cursor.fetchall())

            sql_marked_dates = "SELECT DISTINCT day FROM exp5_case_1 WHERE (vp_asn="+str(vp[0])+" AND vp_ip='"+vp[1]+"')"
            cursor.execute(sql_marked_dates)
            marked_dates = set(cursor.fetchall())

            marked_perc = len(data_dates.intersection(marked_dates))/len(data_dates)
            len_data_dates = len(data_dates)
            len_marked_dates = len(marked_dates)

            args = "(" + str(vp[0]) + ",'" + vp[1] + "',"+ str(len_data_dates) + "," + str(len_marked_dates) + ","
            args += str(marked_perc) + ")"
            sql_insert_stats = "INSERT INTO exp5_case_1_vp_stats VALUES " + args
            cursor.execute(sql_insert_stats)
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("ERROR: Can't connect to DB.")
        print(e)
        exit()


def main(args):
    args = parse_arguments(args)
    config_files = read_experiment_config_files(args.experiment_configs)
    raw_data, vp_routes = get_bgp_data_from_file(config_files, 'data/2018-01-01-exp5.ribs')
    #insert_raw_data_to_db('ovsdb', 'ovs-tester', 'ovs', 'localhost', raw_data)
    add_missing_routes(config_files, vp_routes, args.day)


    with open(args.db_config, 'r') as f:
        db_config = json.load(f)

    case1_results = analyze_experiment5(config_files[5], vp_routes, args.day)
    #insert_analysis_results_to_db('ovsdb', 'ovs-tester', 'localhost', 'localhost', 'exp5_case_1', case1_results)
    update_exp5_stats('ovsdb', 'ovs-tester', 'localhost', 'localhost', case1_results)

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
