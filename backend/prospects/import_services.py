"""
Helpers for the Prospect Excel/CSV import.

Keeps the import flow small and readable:
  * read at most MAX_IMPORT_ROWS data rows from the uploaded file
  * group repeated company rows (existing behaviour) while keeping source row numbers
  * resolve parent company names -> existing DB prospect or another row in the file
  * order rows so parents are created before children (simple DFS)
  * import every company in its own transaction (best-effort import)
"""
import codecs
import csv
import logging
import re
import uuid
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import EmailVerification, Prospect, ProspectImportHistory, assign_lq_to_prospect

logger = logging.getLogger(__name__)

MAX_IMPORT_ROWS = 100
PARENT_NAME_DELIMITERS = re.compile(r'[;|\r\n]+')

STATUS_EXISTS_IN_DB = 'EXISTS_IN_DB'
STATUS_FOUND_IN_FILE = 'FOUND_IN_FILE'
STATUS_MISSING = 'MISSING'
STATUS_CIRCULAR = 'CIRCULAR_DEPENDENCY'

CHILD_STRUCTURES = {'branch', 'subsidiary'}


class ImportFileError(Exception):
    """Raised when the uploaded file cannot be read."""


class RowImportError(Exception):
    """A user-friendly, row-level import failure."""


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def clean_value(value):
    """Return a stripped string; None becomes ''."""
    if value is None:
        return ''
    return str(value).strip()


def collapse_whitespace(value):
    return ' '.join(clean_value(value).split())


def normalize_company_name(value):
    """Exact-match key: trimmed, single-spaced, case-insensitive."""
    return collapse_whitespace(value).casefold()


def parse_parent_company_names(value):
    """Split a parent cell on ';', '|' or newlines. Returns unique display names in order."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        value = '\n'.join(clean_value(v) for v in value)
    names, seen = [], set()
    for part in PARENT_NAME_DELIMITERS.split(str(value)):
        name = collapse_whitespace(part)
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names


def format_serializer_errors(errors_dict, prefix=""):
    msgs = []
    if isinstance(errors_dict, list):
        for i, err in enumerate(errors_dict):
            if isinstance(err, dict) and err:
                msgs.extend(format_serializer_errors(err, f"{prefix}[{i+1}] "))
            elif not isinstance(err, dict):
                msgs.append(f"{prefix}{err}")
    elif isinstance(errors_dict, dict):
        for field_key, errs in errors_dict.items():
            field_name = str(field_key).replace('_', ' ').title()
            if isinstance(errs, dict) or (isinstance(errs, list) and len(errs) > 0 and isinstance(errs[0], dict)):
                msgs.extend(format_serializer_errors(errs, f"{prefix}{field_name} "))
            elif isinstance(errs, list):
                msgs.append(f"{prefix}{field_name}: {', '.join([str(e) for e in errs])}")
            else:
                msgs.append(f"{prefix}{field_name}: {errs}")
    else:
        msgs.append(f"{prefix}{errors_dict}")
    return msgs


def _is_blank_row(values):
    return all(clean_value(v) == '' for v in values)


# ---------------------------------------------------------------------------
# File reading (bounded to MAX_IMPORT_ROWS data rows)
# ---------------------------------------------------------------------------

def read_import_file(uploaded_file, max_rows=MAX_IMPORT_ROWS, headers_only=False):
    """
    Returns (headers, rows, limit_reached).
    rows = [(source_row_number, {header: value})]; header row is Excel row 1.
    Reading stops as soon as a (max_rows + 1)th data row is detected.
    """
    filename = (uploaded_file.name or '').lower()
    if filename.endswith('.csv'):
        return _read_csv(uploaded_file, max_rows, headers_only)
    if filename.endswith('.xlsx'):
        return _read_xlsx(uploaded_file, max_rows, headers_only)
    raise ImportFileError('Only CSV and XLSX files are supported.')


def _collect_rows(row_iter, headers, max_rows):
    rows, limit_reached, source_row = [], False, 1
    for values in row_iter:
        source_row += 1
        if _is_blank_row(values):
            continue
        if len(rows) >= max_rows:
            limit_reached = True
            break
        rows.append((source_row, dict(zip(headers, values))))
    return rows, limit_reached


def _read_csv(uploaded_file, max_rows, headers_only):
    uploaded_file.seek(0)
    try:
        # Streams line by line instead of decoding the entire file into memory.
        reader = csv.reader(codecs.iterdecode(uploaded_file, 'utf-8-sig'))
        headers = [clean_value(h) for h in next(reader, [])]
        if headers_only:
            return headers, [], False
        rows, limit_reached = _collect_rows(reader, headers, max_rows)
    except UnicodeDecodeError:
        raise ImportFileError('CSV file must be UTF-8 encoded.')
    except csv.Error:
        raise ImportFileError('Unable to parse CSV file.')
    return headers, rows, limit_reached


def _read_xlsx(uploaded_file, max_rows, headers_only):
    try:
        import openpyxl
    except ImportError:
        raise ImportFileError('openpyxl is required to parse XLSX files.')
    try:
        uploaded_file.seek(0)
        wb = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
    except Exception:
        raise ImportFileError('Unable to read XLSX file.')
    try:
        ws = wb.active
        row_iter = ws.iter_rows(values_only=True)
        header_row = next(row_iter, None) or ()
        headers = [str(h) if h is not None else '' for h in header_row]
        if headers_only:
            return headers, [], False
        rows, limit_reached = _collect_rows(row_iter, headers, max_rows)
    finally:
        wb.close()
    return headers, rows, limit_reached


# ---------------------------------------------------------------------------
# Grouping (existing behaviour, now keeping source row numbers)
# ---------------------------------------------------------------------------

def group_rows(source_rows, mapping):
    """
    Applies the column mapping and groups rows with the same company name into
    one prospect (contacts/offerings are merged), exactly like the original importer.
    Returns [{'data': {...}, 'source_row_numbers': [..]}].
    """
    grouped = {}
    for source_row, row in source_rows:
        new_row = dict(row)
        for orig, new_key in mapping.items():
            if new_key and new_key != orig:
                new_row[new_key] = row.get(orig)

        key_contacts = []
        c_name = clean_value(new_row.get('contact_name'))
        if c_name:
            key_contacts.append({
                'contact_name': c_name,
                'designation': clean_value(new_row.get('contact_designation')),
                'official_email': clean_value(new_row.get('contact_email')),
                'phone_number': clean_value(new_row.get('contact_phone')),
            })

        offerings = []
        for o_type, o_key in [('Product', 'product'), ('Service', 'service'), ('Solution', 'solution')]:
            val = clean_value(new_row.get(o_key))
            if val:
                offerings.append({'offering_type': o_type, 'name': val})

        parent_names = parse_parent_company_names(new_row.get('parent_company_names'))

        comp_name = clean_value(new_row.get('company_name')).lower()
        if comp_name and comp_name in grouped:
            entry = grouped[comp_name]
            
            # Deduplicate contacts
            for kc in key_contacts:
                if not any(c.get('contact_name') == kc.get('contact_name') and c.get('official_email') == kc.get('official_email') for c in entry['data']['key_contacts']):
                    entry['data']['key_contacts'].append(kc)
            
            # Deduplicate offerings
            for o in offerings:
                if not any(e.get('offering_type') == o.get('offering_type') and e.get('name') == o.get('name') for e in entry['data']['offerings_data']):
                    entry['data']['offerings_data'].append(o)
                    
            entry['source_row_numbers'].append(source_row)
            existing = {n.casefold() for n in entry['parent_names']}
            entry['parent_names'].extend(n for n in parent_names if n.casefold() not in existing)
        else:
            new_row['key_contacts'] = key_contacts
            new_row['offerings_data'] = offerings
            grouped[comp_name or str(uuid.uuid4())] = {
                'data': new_row,
                'source_row_numbers': [source_row],
                'parent_names': parent_names,
            }

    result = []
    for entry in grouped.values():
        if entry['parent_names'] or 'parent_company_names' in entry['data']:
            entry['data']['parent_company_names'] = '; '.join(entry['parent_names'])
        result.append({'data': entry['data'], 'source_row_numbers': entry['source_row_numbers']})
    return result


def build_emails_to_verify(data):
    emails = []
    company_email = clean_value(data.get('official_email_address'))
    if company_email:
        emails.append({'email': company_email, 'status': 'UNVERIFIED', 'type': 'company'})
    for i, contact in enumerate(data.get('key_contacts') or []):
        c_email = clean_value(contact.get('official_email'))
        if c_email:
            emails.append({'email': c_email, 'status': 'UNVERIFIED', 'type': 'contact',
                           'contact_name': contact.get('contact_name'), 'contact_index': i})
    return emails


# ---------------------------------------------------------------------------
# Parent resolution + dependency ordering
# ---------------------------------------------------------------------------

@dataclass
class ImportItem:
    index: int
    data: dict
    source_row_numbers: list
    company_name: str = ''
    key: str = ''
    parent_names: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    parent_resolution: list = field(default_factory=list)
    # [(display_name, normalized_key, status, file_item_index_or_None)]
    parent_refs: list = field(default_factory=list)

    @property
    def first_row(self):
        return self.source_row_numbers[0] if self.source_row_numbers else None


def make_item(index, data, source_row_numbers):
    data = data if isinstance(data, dict) else {}
    item = ImportItem(index=index, data=data, source_row_numbers=list(source_row_numbers))
    item.company_name = clean_value(data.get('company_name'))
    item.key = normalize_company_name(item.company_name)
    item.parent_names = parse_parent_company_names(data.get('parent_company_names'))
    return item


def _name_lookup(queryset, names):
    """Minimal query: normalized company name -> prospect id, only for the given names."""
    names = {collapse_whitespace(n) for n in names if clean_value(n)}
    if not names:
        return {}
    query = Q()
    for name in names:
        query |= Q(company_name__iexact=name)
    lookup = {}
    for pid, cname in queryset.filter(query).order_by('created_at').values_list('id', 'company_name'):
        lookup.setdefault(normalize_company_name(cname), pid)
    return lookup


def visible_prospects(user):
    """Same visibility the Prospect form parent lookup uses (PRE sees own records)."""
    qs = Prospect.objects.all()
    if not user.is_superuser:
        qs = qs.filter(created_by=user.username)
    return qs


def _missing_parent_message(missing, resolved, inaccessible):
    parts = []
    for name in missing:
        if name in inaccessible:
            parts.append(f"parent company '{name}' exists in the database but is not accessible to your account")
        else:
            parts.append(f"parent company '{name}' was not found in the database or uploaded file")
    msg = '; '.join(parts)
    if resolved:
        resolved_txt = ', '.join(f"'{n}'" for n in resolved)
        return f"Parent company {resolved_txt} resolved, but {msg}."
    return msg[0].upper() + msg[1:] + '.'


def analyze_items(items, user):
    """
    Validates names/duplicates/required parents, resolves parent names and returns
    a dependency order (parents before children). Does not write to the database.
    Returns (order, visible_parent_lookup).
    """
    all_parent_names = [n for it in items for n in it.parent_names]
    global_lookup = _name_lookup(Prospect.objects.all(), [it.company_name for it in items] + all_parent_names)
    parent_lookup = _name_lookup(visible_prospects(user), all_parent_names)

    file_index = {}
    for it in items:
        if not it.company_name:
            it.errors.append('Company Name is required.')
            continue
        if it.key in global_lookup:
            it.errors.append('Duplicate company name already in DB.')
        elif it.key in file_index:
            it.errors.append('Duplicate company name within file.')
        else:
            file_index[it.key] = it.index

    for it in items:
        structure = clean_value(it.data.get('company_structure')).casefold()
        if structure in CHILD_STRUCTURES and not it.parent_names:
            it.errors.append('At least one parent company is required for Branch/Subsidiary.')

        missing, resolved, inaccessible = [], [], set()
        for name in it.parent_names:
            key = normalize_company_name(name)
            if it.key and key == it.key:
                it.parent_refs.append((name, key, STATUS_CIRCULAR, None))
                it.parent_resolution.append({'name': name, 'status': STATUS_CIRCULAR})
            elif key in parent_lookup:
                resolved.append(name)
                it.parent_refs.append((name, key, STATUS_EXISTS_IN_DB, None))
                it.parent_resolution.append({'name': name, 'status': STATUS_EXISTS_IN_DB})
            elif key in file_index:
                parent_item = items[file_index[key]]
                resolved.append(name)
                it.parent_refs.append((name, key, STATUS_FOUND_IN_FILE, parent_item.index))
                it.parent_resolution.append({'name': name, 'status': STATUS_FOUND_IN_FILE,
                                             'source_row': parent_item.first_row})
            else:
                missing.append(name)
                if key in global_lookup:
                    inaccessible.add(name)
                it.parent_refs.append((name, key, STATUS_MISSING, None))
                it.parent_resolution.append({'name': name, 'status': STATUS_MISSING})
        if missing:
            it.errors.append(_missing_parent_message(missing, resolved, inaccessible))

    order, cyclic = _dependency_order(items)

    for it in items:
        is_self_ref = any(status == STATUS_CIRCULAR for _, _, status, _ in it.parent_refs)
        if it.index in cyclic or is_self_ref:
            it.errors.append('Circular parent-company dependency detected.')
        if it.index in cyclic:
            for pos, (name, key, status, p_idx) in enumerate(it.parent_refs):
                if status == STATUS_FOUND_IN_FILE and p_idx in cyclic:
                    it.parent_refs[pos] = (name, key, STATUS_CIRCULAR, p_idx)
                    it.parent_resolution[pos] = {'name': name, 'status': STATUS_CIRCULAR,
                                                 'source_row': items[p_idx].first_row}
    return order, parent_lookup


def _dependency_order(items):
    """Post-order DFS over in-file parent links. Returns (order, set_of_cyclic_indices)."""
    deps = {it.index: [p for _, _, status, p in it.parent_refs if status == STATUS_FOUND_IN_FILE]
            for it in items}
    visiting, done = set(), set()
    stack, order, cyclic = [], [], set()

    def visit(i):
        visiting.add(i)
        stack.append(i)
        for p in deps[i]:
            if p in visiting:
                cyclic.update(stack[stack.index(p):])
            elif p not in done:
                visit(p)
        stack.pop()
        visiting.discard(i)
        done.add(i)
        order.append(i)

    for it in items:
        if it.index not in done:
            visit(it.index)
    return order, cyclic


def _failed_parent_reason(items, item, failed, verb):
    for name, _, status, p_idx in item.parent_refs:
        if status in (STATUS_FOUND_IN_FILE, STATUS_CIRCULAR) and p_idx is not None and p_idx in failed:
            row = items[p_idx].first_row
            return (f"Parent company '{name}' from Excel row {row} {verb}, "
                    f"so this dependent company could not be imported.")
    return None


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def build_preview(grouped, user):
    items = [make_item(i, g['data'], g['source_row_numbers']) for i, g in enumerate(grouped)]
    order, _ = analyze_items(items, user)

    failed = set()
    for i in order:
        it = items[i]
        if not it.errors:
            reason = _failed_parent_reason(items, it, failed, 'is not importable')
            if reason:
                it.errors.append(reason)
        if it.errors:
            failed.add(i)

    return [{
        'row_number': it.first_row,
        'source_row_numbers': it.source_row_numbers,
        'data': it.data,
        'validation_status': 'INVALID' if it.errors else 'VALID',
        'errors': it.errors,
        'emails_to_verify': build_emails_to_verify(it.data),
        'parent_resolution': it.parent_resolution,
    } for it in items]


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------

def _sanitize_source_rows(row_payload, fallback):
    rows = []
    for value in row_payload.get('source_row_numbers') or []:
        try:
            rows.append(int(value))
        except (TypeError, ValueError):
            continue
    if not rows:
        try:
            rows = [int(row_payload.get('row_number'))]
        except (TypeError, ValueError):
            rows = [fallback]
    return rows


def _email_check(item, client_emails):
    """Every email present in the row data must be verified VALID (existing rule)."""
    statuses = {}
    print(f"DEBUG _email_check: client_emails={client_emails}")
    for ev in client_emails or []:
        if isinstance(ev, dict) and ev.get('email'):
            statuses[clean_value(ev['email']).casefold()] = ev.get('status')
    required = build_emails_to_verify(item.data)
    print(f"DEBUG _email_check: required={required}, statuses={statuses}")
    for ev in required:
        status = statuses.get(ev['email'].casefold()) or 'UNVERIFIED'
        if status != 'VALID':
            raise RowImportError(f"Email '{ev['email']}' is not verified as VALID (status: {status}).")
        ev['status'] = 'VALID'
    return required


def import_single_row(item, parent_ids, emails, serializer_class, request):
    """Creates one prospect with contacts, offerings, parents, email verifications and LQ assignment
    inside its own transaction; any failure rolls back only this company."""
    user = request.user
    with transaction.atomic():
        if Prospect.objects.filter(company_name__iexact=item.company_name).exists():
            raise RowImportError('Duplicate company name already in DB.')

        data = dict(item.data)
        data.pop('parent_company_names', None)
        data['parent_companies'] = [str(pid) for pid in parent_ids]
        
        merging_names = parse_parent_company_names(data.pop('merging_companies', None))
        dissolved_names = parse_parent_company_names(data.pop('dissolved_companies', None))
        
        acq_companies_raw = data.pop('acquiring_company', None)
        acq_shares_raw = data.pop('acquired_shares', None)
        acquiring_companies_data = []
        if acq_companies_raw:
            c_names = [x.strip() for x in str(acq_companies_raw).split(';') if x.strip()]
            c_shares = [x.strip() for x in str(acq_shares_raw or '').split(';')]
            for idx, c_name in enumerate(c_names):
                share_val = None
                if idx < len(c_shares) and c_shares[idx]:
                    try:
                        share_val = float(c_shares[idx])
                    except ValueError:
                        pass
                
                acq_p = Prospect.objects.filter(company_name__iexact=c_name).first()
                if not acq_p:
                    acq_p = Prospect.objects.create(
                        company_name=c_name,
                        company_structure='Independent',
                        operational_status='Active'
                    )
                acquiring_companies_data.append({
                    'acquiring_company': str(acq_p.id),
                    'acquired_shares': share_val
                })
        data['acquiring_companies_data'] = acquiring_companies_data
        
        acquired_names = parse_parent_company_names(data.pop('acquired_companies', None))
        shareholders_raw = data.pop('shareholders', None)
        market_events_raw = data.pop('market_events', None)
        
        # Pop unsupported relational fields that might still be there
        data.pop('merging_companies', None)
        data.pop('dissolved_companies', None)
        data.pop('acquired_companies', None)
        data.pop('shareholders', None)

        serializer = serializer_class(data=data, context={'request': request, 'is_import': True})
        if not serializer.is_valid():
            raise RowImportError('Validation failed: ' + ' | '.join(format_serializer_errors(serializer.errors)))

        prospect = serializer.save(created_by=user.username)

        for ev in emails:
            contact = None
            if ev.get('type') == 'contact':
                contact = prospect.key_contacts.filter(
                    contact_name=ev.get('contact_name'),
                    official_email=ev.get('email')
                ).first()
            try:
                with transaction.atomic():
                    EmailVerification.objects.create(
                        prospect=prospect,
                        prospect_contact=contact,
                        email_address=ev.get('email'),
                        verification_status='VALID',
                        verified_by=user,
                        verified_at=timezone.now()
                    )
            except IntegrityError:
                # Skip if a duplicate verification record somehow already exists
                pass

        # old acquiring_name logic removed
        
        for m_name in merging_names:
            m_comp = Prospect.objects.filter(company_name__iexact=m_name).first()
            if m_comp: prospect.merging_companies.add(m_comp)
            
        for d_name in dissolved_names:
            d_comp = Prospect.objects.filter(company_name__iexact=d_name).first()
            if d_comp: prospect.dissolved_companies.add(d_comp)
            
        for a_name in acquired_names:
            a_comp = Prospect.objects.filter(company_name__iexact=a_name).first()
            if a_comp:
                a_comp.acquiring_company = prospect
                a_comp.save(update_fields=['acquiring_company'])
                
        if shareholders_raw:
            from .models import ProspectShareholding
            import re
            for sh_part in PARENT_NAME_DELIMITERS.split(str(shareholders_raw)):
                sh_part = sh_part.strip()
                if not sh_part: continue
                try:
                    name_type, perc_str = sh_part.rsplit(':', 1)
                    perc = float(perc_str.strip())
                    m = re.match(r'^(.*?)\s*\((.*?)\)$', name_type.strip())
                    if m:
                        name = m.group(1).strip()
                        type_str = m.group(2).strip().lower()
                    else:
                        name = name_type.strip()
                        type_str = 'other'
                        
                    holder_type = ProspectShareholding.HolderType.OTHER
                    company = None
                    contact = None
                    other_name = None
                    
                    if type_str == 'company':
                        holder_type = ProspectShareholding.HolderType.OTHER
                        other_name = name
                        c = Prospect.objects.filter(company_name__iexact=name).first()
                        if c:
                            holder_type = ProspectShareholding.HolderType.COMPANY
                            company = c
                            other_name = None
                    elif type_str == 'individual':
                        holder_type = ProspectShareholding.HolderType.OTHER
                        other_name = name
                        c = prospect.key_contacts.filter(contact_name__iexact=name).first()
                        if c:
                            holder_type = ProspectShareholding.HolderType.INDIVIDUAL
                            contact = c
                            other_name = None
                    elif type_str in ('government', 'country', 'state'):
                        holder_type = ProspectShareholding.HolderType.OTHER
                        other_name = name
                    else:
                        holder_type = ProspectShareholding.HolderType.OTHER
                        other_name = name
                        
                    ProspectShareholding.objects.create(
                        prospect=prospect,
                        holder_type=holder_type,
                        company=company,
                        contact=contact,
                        other_name=other_name,
                        share_percentage=perc
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse shareholder {sh_part}: {e}")

        if market_events_raw:
            from market_events.models import MarketEvent, MarketEventParticipation
            for event_title in PARENT_NAME_DELIMITERS.split(str(market_events_raw)):
                event_title = event_title.strip()
                if not event_title: continue
                try:
                    event_obj, _ = MarketEvent.objects.get_or_create(event_title=event_title)
                    MarketEventParticipation.objects.get_or_create(
                        market_event=event_obj,
                        prospect=prospect
                    )
                except Exception as e:
                    logger.warning(f"Failed to create/assign market event {event_title}: {e}")

        assign_lq_to_prospect(prospect)
    return prospect


def run_import(rows, request, serializer_class, file_name='', client_limit_reached=False):
    user = request.user
    items, client_emails, overflow = [], {}, []
    processed_source_rows = 0
    limit_reached = bool(client_limit_reached)

    for pos, row_payload in enumerate(rows):
        if not isinstance(row_payload, dict):
            continue
        source_rows = _sanitize_source_rows(row_payload, pos + 1)
        data = row_payload.get('data') if isinstance(row_payload.get('data'), dict) else {}
        if processed_source_rows + len(source_rows) > MAX_IMPORT_ROWS:
            limit_reached = True
            overflow.append({'source_row_numbers': source_rows,
                             'company_name': clean_value(data.get('company_name')),
                             'reason': f'Not processed: exceeds the {MAX_IMPORT_ROWS}-row import limit.'})
            continue
        processed_source_rows += len(source_rows)
        item = make_item(len(items), data, source_rows)
        client_emails[item.index] = row_payload.get('emails_to_verify')
        items.append(item)

    order, parent_cache = analyze_items(items, user)

    created, failed = {}, set()
    imported_rows, not_imported_rows = [], list(overflow)

    def fail(it, reason):
        failed.add(it.index)
        not_imported_rows.append({'source_row_numbers': it.source_row_numbers,
                                  'company_name': it.company_name, 'reason': reason})

    # Group items into dependency levels so independent rows can be imported concurrently
    item_level = {}
    levels = []
    for i in order:
        it = items[i]
        level = 0
        for _, _, status, p_idx in it.parent_refs:
            if status == STATUS_FOUND_IN_FILE:
                level = max(level, item_level.get(p_idx, 0) + 1)
        item_level[i] = level
        while len(levels) <= level:
            levels.append([])
        levels[level].append(i)

    def process_item(i):
        from django.db import connection
        try:
            it = items[i]
            if it.errors:
                return (i, False, ' '.join(it.errors), None)
            
            # Since levels are processed sequentially, file-parents are guaranteed 
            # to be in the 'created' dictionary if they were successfully imported.
            parent_ids = []
            for _, key, status, p_idx in it.parent_refs:
                if status == STATUS_FOUND_IN_FILE:
                    pid = created.get(p_idx)
                    if not pid:
                        return (i, False, f"Parent company '{items[p_idx].company_name}' was not imported.", None)
                    parent_ids.append(pid)
                else:
                    parent_ids.append(parent_cache[key])
            
            emails = _email_check(it, client_emails.get(i))
            prospect = import_single_row(it, parent_ids, emails, serializer_class, request)
            return (i, True, None, prospect.id)
        except RowImportError as e:
            return (i, False, str(e), None)
        except IntegrityError:
            logger.exception('Integrity error importing prospect row %s', items[i].source_row_numbers)
            return (i, False, 'Could not be saved because of a database conflict (possibly a duplicate company).', None)
        except Exception:
            logger.exception('Unexpected error importing prospect row %s', items[i].source_row_numbers)
            return (i, False, 'An unexpected error occurred while importing this row.', None)
        finally:
            connection.close() # Vital to prevent connection pool exhaustion in threads

    from concurrent.futures import ThreadPoolExecutor

    for lvl_items in levels:
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(process_item, lvl_items))
            for i, success, reason, pid in results:
                it = items[i]
                if success:
                    created[i] = pid
                    parent_cache[it.key] = pid
                    imported_rows.append({'source_row_numbers': it.source_row_numbers,
                                          'company_name': it.company_name, 'prospect_id': str(pid)})
                else:
                    fail(it, reason)

    referenced_file_parents = {p for it in items for _, _, status, p in it.parent_refs
                               if status == STATUS_FOUND_IN_FILE}
    parent_auto_created_count = len(referenced_file_parents & set(created))

    sort_key = lambda r: (r['source_row_numbers'] or [0])[0]
    imported_rows.sort(key=sort_key)
    not_imported_rows.sort(key=sort_key)

    if imported_rows and not not_imported_rows:
        history_status, status_text = ProspectImportHistory.Status.COMPLETED, 'completed'
    elif imported_rows:
        history_status, status_text = ProspectImportHistory.Status.PARTIAL, 'completed_with_issues'
    else:
        history_status, status_text = ProspectImportHistory.Status.FAILED, 'failed'

    history_id = None
    try:
        history = ProspectImportHistory.objects.create(
            created_by=user,
            file_name=clean_value(file_name)[:255],
            status=history_status,
            processed_source_rows=processed_source_rows,
            imported_count=len(imported_rows),
            not_imported_count=len(not_imported_rows),
            parent_auto_created_count=parent_auto_created_count,
            limit_reached=limit_reached,
            imported_rows=imported_rows,
            not_imported_rows=not_imported_rows,
        )
        history_id = str(history.id)
    except Exception:
        logger.exception('Failed to save prospect import history')

    return {
        'status': status_text,
        'import_history_id': history_id,
        'max_rows': MAX_IMPORT_ROWS,
        'processed_source_rows': processed_source_rows,
        'limit_reached': limit_reached,
        'imported_count': len(imported_rows),
        'not_imported_count': len(not_imported_rows),
        'parent_auto_created_count': parent_auto_created_count,
        'imported_rows': imported_rows,
        'not_imported_rows': not_imported_rows,
    }


def serialize_history(history):
    return {
        'id': str(history.id),
        'file_name': history.file_name,
        'status': history.status,
        'created_by': history.created_by.username if history.created_by else None,
        'processed_source_rows': history.processed_source_rows,
        'imported_count': history.imported_count,
        'not_imported_count': history.not_imported_count,
        'parent_auto_created_count': history.parent_auto_created_count,
        'limit_reached': history.limit_reached,
        'imported_rows': history.imported_rows,
        'not_imported_rows': history.not_imported_rows,
        'created_at': history.created_at,
    }
