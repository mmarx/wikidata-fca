def write_context_to_file(context, outfile, labels={}):
    def _label(needle):
        if needle in labels:
            return '{} ({})'.format(labels[needle], needle)

        reverse = False
        annotation = ''

        if needle[0] == '^':
            # reverse property
            reverse = True
            needle = needle[1:]

        parts = needle.rsplit('@[', maxsplit=1)

        if len(parts) == 2:
            # handle qualifiers
            qualifier = parts[1][:-1]
            colon = qualifier.index(':')
            pid = qualifier[:colon]
            pq = pid
            if pid in labels:
                pq = '{} ({})'.format(labels[pid], pid)

            annotation = '@[{}:{}]'.format(pq, qualifier[colon + 1:])
        else:
            parts = needle.rsplit('@<', maxsplit=1)

            if len(parts) == 2:
                # handle direct class label
                annotation = '@<{}>'.format(parts[1][:-1])

        prop = parts[0]
        if prop in labels:
            prop = '{} ({})'.format(labels[prop], prop)

        return '{}{}{}'.format('^' if reverse else '',
                               prop, annotation)

    print('B\n', file=outfile)
    print(len(context['objects']), file=outfile)
    print(len(context['attributes']), file=outfile)
    print('', file=outfile)

    for obj in context['objects']:
        print(_label(obj), file=outfile)

    for att in context['attributes']:
        print(_label(att), file=outfile)

    for obj in context['objects']:
        print(*['X' if att in context['incidence'][obj]
                else '.'
                for att in context['attributes']],
              sep='', file=outfile)
