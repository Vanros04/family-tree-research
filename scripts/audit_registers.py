#!/usr/bin/env python3
"""Read-only checks of optional genealogy CSV registers; not an evidence verdict."""
import argparse
import csv
import json
from pathlib import Path

SCHEMAS = {
    'people': ('person_id', 'label'),
    'sources': ('source_id', 'independence_group', 'locator', 'kind'),
    'claims': ('claim_id', 'person_id', 'statement', 'source_ids', 'status', 'note'),
    'relationships': ('relationship_id', 'from_person_id', 'to_person_id',
                      'relation', 'claim_ids', 'status', 'note'),
}
STATUSES = {'hypothesis', 'single-source', 'corroborated', 'unresolved', 'contradicted'}
UNKNOWN = {'', 'unknown', 'unresolved', '?'}


def references(value):
    return list(dict.fromkeys(x.strip() for x in value.split('|') if x.strip()))


def audit(directory):
    errors, warnings, skipped, manual_review = [], [], [], []
    tables = {}
    for name, fields in SCHEMAS.items():
        path = directory / (name + '.csv')
        table = {}
        tables[name] = table
        if not path.is_file():
            skipped.append(name)
            continue
        try:
            with path.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream, strict=True)
                if not set(fields).issubset(reader.fieldnames or []):
                    errors.append(f'{name}: missing required columns')
                    continue
                if len(reader.fieldnames) != len(set(reader.fieldnames)):
                    errors.append(f'{name}: duplicate column names')
                    continue
                for number, raw in enumerate(reader, 2):
                    if None in raw or any(v is None for v in raw.values()):
                        errors.append(f'{name}:{number}: malformed row')
                        continue
                    row = {k: v.strip() for k, v in raw.items()}
                    if not any(row.values()):
                        continue
                    key = row[fields[0]]
                    if not key or key in table:
                        errors.append(f'{name}:{number}: empty or duplicate ID {key!r}')
                        continue
                    table[key] = row
        except (OSError, UnicodeError, csv.Error) as exc:
            errors.append(f'{name}: {type(exc).__name__}')

    def require(table, key, context):
        if not key or key not in tables[table]:
            errors.append(f'{context}: missing {table} reference {key!r}')

    def check_status(row, ids, context):
        status = row['status']
        if status not in STATUSES:
            errors.append(f'{context}: unsupported status {status!r}')
        if status in {'single-source', 'corroborated'} and not ids:
            errors.append(f'{context}: evidence status without cited sources')
        groups = set()
        for key in ids:
            source = tables['sources'].get(key)
            if source:
                group = source['independence_group']
                if group.casefold() not in UNKNOWN:
                    groups.add(group)
                else:
                    warnings.append(f'{context}: source {key} has unknown independence')
        if status == 'corroborated' and len(groups) < 2:
            errors.append(f'{context}: corroborated needs two known cited independence groups')
        if status == 'corroborated':
            manual_review.append(f'{context}: verify relevance and independence manually')

    for key, row in tables['sources'].items():
        if not row['locator']:
            errors.append(f'sources:{key}: missing locator')
    for key, row in tables['people'].items():
        if not row['label']:
            errors.append(f'people:{key}: missing label')
    for key, row in tables['claims'].items():
        context = 'claims:' + key
        require('people', row['person_id'], context)
        if not row['statement']:
            errors.append(f'{context}: missing statement')
        ids = references(row['source_ids'])
        for source_id in ids:
            require('sources', source_id, context)
        check_status(row, ids, context)
    for key, row in tables['relationships'].items():
        context = 'relationships:' + key
        require('people', row['from_person_id'], context)
        require('people', row['to_person_id'], context)
        if not row['relation']:
            errors.append(f'{context}: missing relation')
        if row['from_person_id'] == row['to_person_id']:
            errors.append(f'{context}: self relationship requires review')
        ids = []
        for claim_id in references(row['claim_ids']):
            require('claims', claim_id, context)
            if claim_id in tables['claims']:
                ids.extend(references(tables['claims'][claim_id]['source_ids']))
        check_status(row, set(ids), context)
    if skipped:
        warnings.append('Not checked (missing registers): ' + ', '.join(skipped))
    if not any(tables.values()):
        warnings.append('No populated rows: evidence has not been checked')
    return {'counts': {k: len(v) for k, v in tables.items()},
            'skipped': skipped, 'errors': errors, 'warnings': warnings,
            'manual_review': manual_review,
            'scope': 'CSV integrity only; no handwriting, identity or kinship validation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case_directory', type=Path)
    args = parser.parse_args()
    if not args.case_directory.is_dir():
        parser.error('case_directory must be an existing directory')
    result = audit(args.case_directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['errors'] or result['warnings'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
