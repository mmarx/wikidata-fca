#!/usr/bin/env python3

import json
import argparse
from time import sleep
from enum import Enum
from pickle import Unpickler
from collections import defaultdict

from contexts import write_context_to_file
from wikidata import context_from_dump, is_not_deprecated
from wikidata import has_claims, has_qualifiers, maybe_entity_value
from wikidata import all_direct_instances_in_class, format_datavalue
from wikidata import all_direct_classes_for_values_of, has_meaningful_value


class Colouring(Enum):
    none = 1
    direction = 2
    qualifiers = 3
    classes = 4


PROPERTIES = []
COLOURINGS = {
    'none': Colouring.none,
    'direction': Colouring.direction,
    'qualifiers': Colouring.qualifiers,
    'classes': Colouring.classes,
    }


def colour_none(subject, prop, **kwargs):
    return {subject: {prop}}


def colour_direction(subject, prop, claim, **kwargs):
    results = colour_none(subject=subject, prop=prop, claim=claim, **kwargs)
    value = maybe_entity_value(claim)

    if value:
        results[value] = {'^{}'.format(prop)}

    return results


def colour_qualifiers(subject, prop, claim, labels, **kwargs):
    def _coloured(prop, pid, qualifier, reverse=False):
        return '{}{}@[{}:{}]'.format('^' if reverse else '',
                                     prop,
                                     pid,
                                     format_datavalue(qualifier, labels))

    if not has_qualifiers(claim):
        return colour_direction(subject=subject, prop=prop, claim=claim, labels=labels, **kwargs)

    results = {subject: set([])}
    value = maybe_entity_value(claim)
    if value:
        results[value] = set([])

    for pid, qualifiers in claim['qualifiers'].items():
        for qualifier in qualifiers:
            results[subject] |= {_coloured(prop, pid, qualifier)}
            if value:
                results[value] |= {_coloured(prop, pid, qualifier,
                                             reverse=True)}

    return results

def colour_classes(subject, prop, claim, labels, instances, **kwargs):
    value = maybe_entity_value(claim)

    if not value or not value in instances:
        return colour_direction(subject=subject, prop=prop, claim=claim,
                                labels=labels, instances=instances, **kwargs)

    results = {subject: set([]),
               value: set([]),
    }

    for qid in instances[value]:
        label = qid

        if qid in labels:
            label = '{} ({})'.format(labels[qid], qid)

        edge = '{}@<{}>'.format(prop, label)
        results[subject] |= {edge}
        if value:
            results[value] |= {'^{}'.format(edge)}

    return results


COLOURING_MAP = {
    Colouring.none: colour_none,
    Colouring.direction: colour_direction,
    Colouring.qualifiers: colour_qualifiers,
    Colouring.classes: colour_classes,
    }


def process_properties(labels,
                       instances,
                       subclasses,
                       properties=[],
                       colouring=Colouring.none,
                       filter_property=None,
                       filter_value=None,
                       filter_entities=None,
                       **kwargs):
    def process_entity(eid, entity):
        def _matches(pid):
            return all([not properties or pid in properties,
                        not filter_entities or pid in filter_entities,
            ])


        _colour = COLOURING_MAP[colouring]
        result = defaultdict(set)
        bg = {}

        if filter_entities is not None and eid not in filter_entities:
            return result, bg

        if filter_value is not None:
            if filter_property not in entity['claims']:
                return result, bg

            found = False
            for claim in entity['claims'][filter_property]:
                if is_not_deprecated(claim):
                    value = maybe_entity_value(claim)
                    if not value:
                        continue
                    elif value == filter_value:
                        found = True
                    elif (value in subclasses and
                          filter_value in subclasses[value]):
                        found = True
            if not found:
                return result, bg

        for prop, claims in entity['claims'].items():
            if _matches(prop):
                claimed = False
                for claim in claims:
                    if (is_not_deprecated(claim) and
                        has_meaningful_value(claim)):
                        coloured = _colour(subject=eid,
                                           prop=prop,
                                           claim=claim,
                                           labels=labels,
                                           instances=instances,
                                           subclasses=subclasses)


                        if filter_entities is not None:
                            value = maybe_entity_value(claim)
                            if value and value not in filter_entities:
                                continue

                        for ent in coloured:
                            result[ent] |= coloured[ent]

        return result, bg
    return process_entity


def postprocess(labels,
                instances,
                subclasses,
                properties=[],
                colouring=Colouring.none,
                filter_property=None,
                filter_value=None,
                filter_entities=None):
    def process_context(context, **kwargs):
        result = kwargs
        result['context'] = context
        result['labels'] = labels

        return result
    return process_context

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate a formal context '
                                     '(in Burmeister format) from a Wikidata '
                                     'JSON dump')
    parser.add_argument('dump',
                        help='path to Wikidata dump file')
    parser.add_argument('context',
                        help='path to output context file')
    parser.add_argument('--indexes',
                        required=True, dest='indexes',
                        help='path to helper indexes file')
    parser.add_argument('--property', '-p',
                        action='append', metavar='Pid',
                        dest='properties', default=[],
                        help='include property Pid in the context')
    parser.add_argument('--properties-in-class',
                        action='append', metavar='Qid',
                        dest='qids', default=[],
                        help='add direct instances of class Qid to context')
    parser.add_argument('--colouring',
                        choices=COLOURINGS.keys(), default='none',
                        help='use given colouring type')
    parser.add_argument('--item-filter-property',
                        metavar='Pid', dest='filter_property',
                        help='use property Pid as background knowledge')
    parser.add_argument('--item-filter-value',
                        metavar='Value', dest='filter_value',
                        help='use value Value as background knowledge')
    parser.add_argument('--language',
                        metavar='Lang', default='en',
                        help='include labels in language Lang')
    parser.add_argument('--entities-from-file',
                        metavar='Eidfile',
                        dest='eidfile', default=None,
                        help='restrict entities to those in Eidfile')

    args = parser.parse_args()
    properties = args.properties

    for qid in args.qids:
        properties += all_direct_instances_in_class(qid)

    colouring = COLOURINGS[args.colouring]
    kwargs = {'properties': properties,
              'colouring': COLOURINGS[args.colouring],
              'filter_property': args.filter_property,
              'filter_value': args.filter_value,
              }

    with open(args.indexes, 'rb') as idxfile:
        pickle = Unpickler(idxfile)
        indexes = pickle.load()
        kwargs.update(indexes)

    if args.eidfile is not None:
        entities = set([])
        with open(args.eidfile, 'r') as eidfile:
            for line in eidfile:
                entities |= {line.strip()}

        kwargs.update({'filter_entities': entities})

    process_entity = process_properties(**kwargs)
    result = context_from_dump(dump=args.dump,
                               properties_for_entity=process_entity,
                               postprocess=postprocess(**kwargs))

    with open(args.context, 'w') as outfile:
        write_context_to_file(outfile=outfile, **result)
