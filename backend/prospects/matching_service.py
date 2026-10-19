import email.utils
import logging
import re
from typing import Optional, Dict, Any, List, Set
from django.db.models import Q
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')


def extract_clean_email(raw_address: Optional[str]) -> Optional[str]:
    """
    Extracts and normalizes an email address from a header like
    'Priya Sharma <priya@example.com>' or 'contact@example.com'.
    Returns lowercased email string or None if unparseable.
    """
    if not raw_address or not isinstance(raw_address, str):
        return None

    # Use email.utils.parseaddr for RFC-compliant header parsing
    _, parsed_addr = email.utils.parseaddr(raw_address.strip())
    if parsed_addr and '@' in parsed_addr:
        clean = parsed_addr.strip().lower()
        if EMAIL_REGEX.match(clean):
            return clean

    # Fallback to regex extraction
    matches = EMAIL_REGEX.findall(raw_address)
    if matches:
        return matches[0].strip().lower()

    return None


class ProspectMatcher:
    """
    High-performance canonical matching service for identifying prospects and
    key contacts from email addresses.

    Preloads candidate authorized prospects and contacts into memory dicts
    for O(1) lookup per message without executing repeated database queries.
    Enforces role-based visibility and LQ pipeline distribution boundaries.
    """

    def __init__(self, user=None):
        self.user = user
        self.company_emails: Dict[str, List[Any]] = {}
        self.contact_emails: Dict[str, List[Any]] = {}
        self.prospect_lq_map: Dict[Any, int] = {}
        self._build_index()

    def _get_authorized_prospect_ids(self) -> Optional[Set[Any]]:
        """
        Determines the set of Prospect IDs visible to the current user.
        Returns None if user has unrestricted access (superuser or MANAGER).
        Returns a set of UUIDs if restricted (PRE or LQ).
        """
        if not self.user or not self.user.is_authenticated:
            return set()

        if self.user.is_superuser:
            return None

        role = getattr(getattr(self.user, 'profile', None), 'role', None)
        if role == 'MANAGER':
            return None

        from prospects.models import Prospect
        from prospects.views import apply_lq_distribution_filter

        qs = Prospect.objects.all()
        if role == 'PRE':
            qs = qs.filter(created_by=self.user.username)
        elif role == 'LQ':
            qs = apply_lq_distribution_filter(qs, self.user, 'id__')
        else:
            return set()

        return set(qs.values_list('id', flat=True))

    def _build_index(self):
        """Preload active prospects and key contacts within the user's scope."""
        from prospects.models import Prospect, ProspectContact, LeadQualification

        auth_ids = self._get_authorized_prospect_ids()

        prospects_qs = Prospect.objects.all()
        contacts_qs = ProspectContact.objects.select_related('prospect').all()

        if auth_ids is not None:
            prospects_qs = prospects_qs.filter(id__in=auth_ids)
            contacts_qs = contacts_qs.filter(prospect_id__in=auth_ids)

        # Preload prospect UUID to LeadQualification ID map
        try:
            lq_qs = LeadQualification.objects.all()
            if auth_ids is not None:
                lq_qs = lq_qs.filter(prospect_id__in=auth_ids)
            self.prospect_lq_map = dict(lq_qs.values_list('prospect_id', 'id'))
        except Exception:
            self.prospect_lq_map = {}

        # Index company official emails
        for p in prospects_qs.only('id', 'company_name', 'official_email_address'):
            if p.official_email_address:
                norm = p.official_email_address.strip().lower()
                if norm:
                    self.company_emails.setdefault(norm, []).append(p)

        # Index contact official emails
        for c in contacts_qs.only('id', 'contact_name', 'official_email', 'prospect_id', 'prospect__company_name'):
            if c.official_email:
                norm = c.official_email.strip().lower()
                if norm:
                    self.contact_emails.setdefault(norm, []).append(c)

    def match_address(self, raw_address: Optional[str], subject: str = '', snippet: str = '') -> Dict[str, Any]:
        """
        Matches a raw or normalized email address against authorized prospects and contacts.
        Returns a consistent metadata dictionary.
        """
        clean_email = extract_clean_email(raw_address)
        default_res = {
            'prospect_match': False,
            'prospect_match_type': None,
            'prospect_id': None,
            'prospect_lq_id': None,
            'prospect_company_name': None,
            'prospect_contact_id': None,
            'prospect_contact_name': None,
            'prospect_tags': [],
            'ambiguous': False,
        }

        if not clean_email:
            return default_res

        # Rule 8: Prefer an exact, unambiguous key-person match
        matching_contacts = self.contact_emails.get(clean_email, [])
        if matching_contacts:
            distinct_prospect_ids = {c.prospect_id for c in matching_contacts if c.prospect}
            primary_contact = None
            if len(distinct_prospect_ids) > 1:
                # Ambiguous across multiple prospects - attempt to establish via recent outreach
                try:
                    from prospects.models import OutreachEmailRecipient
                    recent_outreach = (
                        OutreachEmailRecipient.objects.filter(
                            email_address__iexact=clean_email,
                            prospect_contact__in=matching_contacts
                        )
                        .select_related('prospect_contact__prospect', 'prospect_contact')
                        .order_by('-id')
                        .first()
                    )
                    if recent_outreach and recent_outreach.prospect_contact:
                        primary_contact = recent_outreach.prospect_contact
                    else:
                        candidate_prospect_ids = [c.prospect_id for c in matching_contacts if c.prospect_id]
                        recent_oe = (
                            OutreachEmailRecipient.objects.filter(
                                email_address__iexact=clean_email,
                                outreach_email__prospect_id__in=candidate_prospect_ids
                            )
                            .select_related('outreach_email__prospect')
                            .order_by('-id')
                            .first()
                        )
                        if recent_oe and recent_oe.outreach_email and recent_oe.outreach_email.prospect_id:
                            matched_cs = [c for c in matching_contacts if c.prospect_id == recent_oe.outreach_email.prospect_id]
                            if matched_cs:
                                primary_contact = matched_cs[0]
                except Exception:
                    pass

                # If still unresolved, check if subject or snippet mentions the company name
                if primary_contact is None and (subject or snippet):
                    text_context = f"{subject} {snippet}".lower()
                    for c in matching_contacts:
                        if c.prospect and c.prospect.company_name.strip().lower() in text_context:
                            primary_contact = c
                            break
            else:
                primary_contact = matching_contacts[0]

            if primary_contact and primary_contact.prospect:
                prospect = primary_contact.prospect
                lq_id = self.prospect_lq_map.get(prospect.id)
                if not lq_id and hasattr(prospect, 'lead_qualification') and prospect.lead_qualification:
                    lq_id = prospect.lead_qualification.id
                return {
                    'prospect_match': True,
                    'prospect_match_type': 'key_person',
                    'prospect_id': str(prospect.id),
                    'prospect_lq_id': lq_id,
                    'prospect_company_name': prospect.company_name,
                    'prospect_contact_id': str(primary_contact.id),
                    'prospect_contact_name': primary_contact.contact_name,
                    'prospect_tags': [
                        {'type': 'company', 'label': prospect.company_name},
                        {'type': 'key_person', 'label': primary_contact.contact_name},
                    ],
                    'ambiguous': False,
                }
            elif len(distinct_prospect_ids) > 1:
                return {**default_res, 'ambiguous': True}

        # Rule 3: Match company official email
        matching_companies = self.company_emails.get(clean_email, [])
        if matching_companies:
            is_ambiguous = False
            prospect = None

            if len(matching_companies) == 1:
                prospect = matching_companies[0]
            else:
                names = {c.company_name.strip().lower() for c in matching_companies}
                if len(names) == 1:
                    prospect = matching_companies[0]
                else:
                    is_ambiguous = True
                    # 1. Attempt to establish match via prior outreach communication
                    try:
                        from prospects.models import OutreachEmailRecipient
                        recent_outreach = (
                            OutreachEmailRecipient.objects.filter(
                                email_address__iexact=clean_email,
                                outreach_email__prospect__in=matching_companies
                            )
                            .select_related('outreach_email__prospect')
                            .order_by('-id')
                            .first()
                        )
                        if recent_outreach and recent_outreach.outreach_email and recent_outreach.outreach_email.prospect:
                            prospect = recent_outreach.outreach_email.prospect
                            is_ambiguous = False
                    except Exception:
                        pass

                    # 2. Check if subject or snippet references one of the company names
                    if is_ambiguous and (subject or snippet):
                        text_context = f"{subject} {snippet}".lower()
                        for c in matching_companies:
                            if c.company_name.strip().lower() in text_context:
                                prospect = c
                                is_ambiguous = False
                                break

            if prospect:
                lq_id = self.prospect_lq_map.get(prospect.id)
                if not lq_id and hasattr(prospect, 'lead_qualification') and prospect.lead_qualification:
                    lq_id = prospect.lead_qualification.id
                return {
                    'prospect_match': True,
                    'prospect_match_type': 'company',
                    'prospect_id': str(prospect.id),
                    'prospect_lq_id': lq_id,
                    'prospect_company_name': prospect.company_name,
                    'prospect_contact_id': None,
                    'prospect_contact_name': None,
                    'prospect_tags': [
                        {'type': 'company', 'label': prospect.company_name},
                    ],
                    'ambiguous': False,
                }
            elif is_ambiguous:
                return {**default_res, 'ambiguous': True}

        return default_res

    def get_authorized_candidate_emails(self) -> List[str]:
        """
        Returns list of all authorized company and key contact emails
        for constructing Gmail search queries.
        """
        all_emails = set(self.company_emails.keys()) | set(self.contact_emails.keys())
        return sorted([e for e in all_emails if e])
