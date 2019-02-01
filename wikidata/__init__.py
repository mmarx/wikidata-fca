import json
import requests
from collections import defaultdict

SPARQL_ENDPOINT = 'https://query.wikidata.org/sparql'
TOOL_BANNER = '#TOOL:conexp-clj Python Helper\n{}'

PROPERTY_INSTANCE_OF = 'P31'
PROPERTY_SUBCLASS_OF = 'P279'

def sparql_query(query):
    """return the results of the sparql query `query`."""
    request = requests.get(SPARQL_ENDPOINT,
                           params={'query': TOOL_BANNER.format(query),
                                   'format': 'json'})
    request.raise_for_status()
    return request.json()


def _instance_query_for_class(qid, language, direct=True):
    """return the instance query for all instances of the class
    `qid`. When `direct` is `False`, also return instances of
    subclasses.
    """
    return """SELECT ?qid ?qidLabel WHERE {{
    ?qid {subclass}wdt:{instance} wd:{qid} .
    SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}" . }}
}}""".format(
        subclass=('' if direct else 'wdt:{}*/'.format(PROPERTY_SUBCLASS_OF)),
        instance=PROPERTY_INSTANCE_OF,
        qid=qid,
        language=language
    )


def _classes_query_for_values_of(pid):
    """return then classes query for all direct classes of values of
    `pid`.
    """
    return """SELECT ?qid WHERE {
    hint:Query hint:optimizer "None".
    ?item wdt:{}/wdt:P31 ?class .
} GROUP BY ?qid""".format(pid)


def _entity_id_from_uri(uri):
    return uri[uri.rfind('/') + 1:]


def _labelled_map_from_bindings(results, field, transform=_entity_id_from_uri):
    label = '{}Label'.format(field)
    bindings = {}

    for binding in results['results']['bindings']:
        value = transform(binding[field]['value'])
        bindings[value] = binding[label]['value']

    return bindings


def _unlabelled_list_from_bindings(results, field, transform=_entity_id_from_uri):
    bindings = []

    for binding in results['results']['bindings']:
        value = transform(binding[field]['value'])
        bindings.append(value)

    return bindings


def all_direct_instances_in_class(qid, language='en'):

    """return a map of all Qids and labels of direct instances in the
    class given by `qid`.
    """
    result = sparql_query(_instance_query_for_class(qid, language))
    return _labelled_map_from_bindings(result, 'qid')


def all_direct_classes_for_values_of(pid):
    """return a list of all Qids that are direct classes of some value of
    the property given by `pid`
    """
    result = sparql_query(_classes_query_for_values_of(pid))
    return _unlabelled_list_from_bindings(result, 'qid')


def all_instances_in_class(qid, language='en'):
    """return a map of all Qids and labels of instances of some subclass
       of the class given by `qid`.
    """
    result = sparql_query(_instance_query_for_class(qid, language,
                                                    direct=False))
    return _labelled_map_from_bindings(result, 'qid')


def process_wikidata_dump(dump):
    with open(dump, 'r') as dumpfile:
        for line in dumpfile:
            try:
                entity = json.loads(line[:-2])
            except json.decoder.JSONDecodeError:
                continue

            yield entity


def context_from_dump(dump,
                      properties_for_entity,
                      postprocess):
    context = {'objects': set([]),
               'attributes': set([]),
               'incidence': defaultdict(set)}

    for entity in process_wikidata_dump(dump):
        eid = entity['id']

        properties, background = properties_for_entity(eid, entity)

        for eid, props in properties.items():
            context['objects'] |= {eid}
            context['attributes'] |= set(props)
            context['incidence'][eid] |= set(props)

        for eid, props in background.items():
            try:
                context['background'][eid] &= set(props)
            except KeyError:
                try:
                    context['background'][eid] = set(props)
                except KeyError:
                    context['background'] = {eid: set(props)}

    return postprocess(context)


def has_claims(entity):
    return entity['claims']


def references(claim):
    return len(claim['references'])


def is_not_deprecated(claim):
    return claim['rank'] != 'deprecated'


def has_meaningful_value(claim):
    return claim['mainsnak']['snaktype'] not in ['novalue', 'somevalue']


def has_qualifiers(claim):
    return 'qualifiers' in claim and claim['qualifiers']


def maybe_entity_value(claim):
    return format_entityid(claim['mainsnak'], labels=None)


def format_entityid(snak, labels=None, **kwargs):
    if snak['snaktype'] in ['novalue', 'somevalue']:
        return

    if snak['datavalue']['type'] != 'wikibase-entityid':
        return

    value = snak['datavalue']['value']

    result = ''
    if 'id' in value:
        result = value['id']
    elif value['entity-type'] == 'item':
        result = 'Q{}'.format(value['numeric-id'])
    elif value['entity-type'] == 'property':
        result = 'P{}'.format(value['numeric-id'])

    if labels is not None and result in labels:
        result = '{} ({})'.format(labels[result], result)

    return result


PROLEPTIC_GREGORIAN_CALENDER = 'Q1985727'


def format_timestamp(snak, labels):
    value = snak['datavalue']['value']
    calendarid = _entity_id_from_uri(value['calendarmodel'])

    if calendarid == PROLEPTIC_GREGORIAN_CALENDER:
        calendar = ''
    elif calendarid in labels:
        calendar = ' ({})'.format(labels[calendarid])
    else:
        calender = ' ({})'.format(calendarid)

    stamp = value['time'][:(value['time'].index('T'))]  # days
    precision = value['precision']

    if precision < 11:      # months
        stamp = stamp[:stamp.rfind('-')]

    if precision < 10:      # years
        stamp = stamp[:stamp.rfind('-')]

    return '{}{}'.format(stamp, calendar)


def format_quantity(snak, labels):
    value = snak['datavalue']['value']
    result = value['amount']

    if ('upperbound' in value and
        'lowerbound' in value):
        result += ' [{}--{}]'.format(value['lowerbound'],
                                     value['upperbound'])

    if value['unit'] != '1':
        unit = _entity_id_from_uri(value['unit'])
        try:
            result += ' {}'.format(labels[unit])
        except KeyError:
            result += ' {}'.format(unit)

    return result


def format_globecoordinate(snak, labels):
    value = snak['datavalue']['value']
    globe = _entity_id_from_uri(value['globe'])
    value['globe'] = labels[globe] if globe in labels else globe

    return ('{latitude}N {longitude}W +-{precision} ' +
            '({globe})'.format_map(value))


def format_monolingualtext(snak, **kwargs):
    return snak['datavalue']['value']['text']


def format_string(snak, **kwargs):
    return snak['datavalue']['value']


DATATYPE_FORMATTERS = {
    'wikibase-item': format_entityid,
    'wikibase-property': format_entityid,
    'time': format_timestamp,
    'quantity': format_quantity,
    'globe-coordinate': format_globecoordinate,
    'monolingualtext': format_monolingualtext,
    'string': format_string,
    'commonsMedia': format_string,  # hacky, but works
    'external-id': format_string,   # same here
    'math': format_string,          # once more
    'url': format_string,           # and yet another one
    }


__seen_datatypes__ = []


def format_datavalue(snak, labels):
    if snak['snaktype'] == 'somevalue':
        return '<somevalue>'

    if snak['snaktype'] == 'novalue':
        return '<novalue>'

    if snak['snaktype'] != 'value':
        raise ValueError("expected a `value' snak")

    datatype = snak['datatype']
    if datatype in DATATYPE_FORMATTERS:
        return DATATYPE_FORMATTERS[datatype](snak=snak, labels=labels)

    if datatype not in __seen_datatypes__:
        print("unknown datatype `{}'".format(datatype))
        __seen_datatypes__.append(datatype)

    # fallback
    return repr(snak['datavalue']['value'])


def write_json_to_file(entities, outfile):
    with open(outfile, 'w') as jfile:
        print('[', file=jfile)

        first = True
        for eid, entity in entities.items():
            if not first:
                print(',\n', json.dumps(entity), file=jfile, end='', sep='')
            else:
                print(json.dumps(entity), file=jfile, end='', sep='')
                first = False

        print('\n]', file=jfile)
