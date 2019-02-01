#!/usr/bin/env python3

import argparse
from pickle import Pickler
from collections import defaultdict
from wikidata import process_wikidata_dump, maybe_entity_value
from wikidata import PROPERTY_SUBCLASS_OF, PROPERTY_INSTANCE_OF


def transitive_closure(relation):
    relation = dict(relation)
    changed = True
    while changed:
        changed = False
        step = defaultdict(set)

        for item, successors in relation.items():
            step[item] = successors.copy()
            for successor in successors:
                try:
                    step[item] |= relation[successor]
                except KeyError:
                    # successor has no further successors, don't need to close
                    pass

            if step[item] - relation[item]:
                changed = True

        if changed:
            relation = dict(step)

    return relation


def direct_relations_from_dump(dump, language='en'):
    labels = {}
    instances = defaultdict(set)
    subclasses = defaultdict(set)

    for entity in process_wikidata_dump(dump):
        eid = entity['id']

        if 'labels' in entity:
            if language in entity['labels']:
                labels[eid] = entity['labels'][language]['value']

        if PROPERTY_SUBCLASS_OF in entity['claims']:
            for claim in entity['claims'][PROPERTY_SUBCLASS_OF]:
                superclass = maybe_entity_value(claim)
                if superclass:
                    subclasses[eid] |= {superclass}

        if PROPERTY_INSTANCE_OF in entity['claims']:
            for claim in entity['claims'][PROPERTY_INSTANCE_OF]:
                klass = maybe_entity_value(claim)
                if klass:
                    instances[eid] |= {klass}

    # now compute the transitive closure
    return labels, instances, subclasses


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='extract a helper indexes ' +
                                     'file from a Wikidata dump')
    parser.add_argument('dump',
                        help='path to Wikidata dump file')
    parser.add_argument('output',
                        help='path to output context file')
    parser.add_argument('--language',
                        metavar='Lang', default='en',
                        help='include labels in language Lang')

    args = parser.parse_args()
    labels, instances, subclasses = direct_relations_from_dump(
        args.dump, language=args.language)
    transitive_subclasses = transitive_closure(subclasses)

    with open(args.output, 'wb') as outfile:
        pickle = Pickler(outfile)
        pickle.dump({'labels': labels,
                     'instances': instances,
                     'subclasses': transitive_subclasses,
        })
