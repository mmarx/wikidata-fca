#!/usr/bin/env python3

import json
import argparse
from collections import defaultdict

from wikidata import process_wikidata_dump, is_not_deprecated
from wikidata import has_claims, has_qualifiers, maybe_entity_value
from wikidata import all_direct_instances_in_class, format_datavalue
from wikidata import all_direct_classes_for_values_of, has_meaningful_value

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate statistics from a JSON dump')
    parser.add_argument('dump',
                        help='path to Wikidata dump file')
    parser.add_argument('--properties-in-class',
                        action='append', metavar='Qid',
                        dest='qids', default=[],
                        help='count formal properties defined by class Qid')
    parser.add_argument('--entities-from-file',
                        metavar='Eidfile',
                        dest='eidfile', default=None,
                        help='restrict entities to those in Eidfile')

    entities = set([])
    args = parser.parse_args()

    if args.eidfile is not None:
        with open(args.eidfile, 'r') as eidfile:
            for line in eidfile:
                entities |= {line.strip()}

    stats = {'__all__': { 'properties': set([]),
                          'items': set([]),
                          'statements': 0,
                          }
             }
    props = defaultdict(set)

    for qid in args.qids:
        stats[qid] = { 'properties': all_direct_instances_in_class(qid),
                       'items': set([]),
                       'statements': 0,
                       }

        for pid in stats[qid]['properties']:
            props[pid] |= {qid}

    props = dict(props)
    for entity in process_wikidata_dump(args.dump):
        eid = entity['id']

        if entities and eid not in entities:
            continue

        for prop, claims in entity['claims'].items():
            if entities and prop not in entities:
                continue

            if props:
                if prop not in props:
                    continue

                for qid in props[prop]:
                    stats[qid]['items'] |= {eid}

            stats['__all__']['items'] |= {eid}
            stats['__all__']['properties'] |= {prop}

            for claim in claims:
                if (is_not_deprecated(claim) and
                    has_meaningful_value(claim)):

                    value = maybe_entity_value(claim)

                    if value:
                        if entities and value not in entities:
                            continue
                        stats['__all__']['items'] |= {value}
                    stats['__all__']['statements'] += 1

                    if props:
                        for qid in props[prop]:
                            if value:
                                stats[qid]['items'] |= {value}
                            stats[qid]['statements'] += 1


    for qid, stat in stats.items():
        print('class {}: {} items, {} properties, {} statements'.format(
            qid,
            len(stat['items']),
            len(stat['properties']),
            stat['statements']))
