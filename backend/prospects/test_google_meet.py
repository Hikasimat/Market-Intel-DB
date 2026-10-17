"""Google Calendar authorization + Google Meet scheduling tests.

Every Google call is mocked at the urllib layer: no live API calls, no real invitations.
"""
import io
import json
import urllib.error
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

import os
import utils.encryption as encryption

if not os.environ.get('MAIL_CREDENTIALS_ENCRYPTION_KEY'):
    os.environ['MAIL_CREDENTIALS_ENCRYPTION_KEY'] = encryption.Fernet.generate_key().decode('utf-8')

from accounts import calendar_services as cal
from accounts.models import GoogleCalendarCredentials, GoogleMailCredentials
from accounts.oauth_services import GoogleOAuthService
from prospects.models import LeadQualification, Meeting, Prospect, ProspectContact

CAL_SCOPE = 'https://www.googleapis.com/auth/calendar.events'
MEET_URL = 'https://meet.google.com/abc-defg-hij'
OAUTH_SETTINGS = dict(
    GOOGLE_OAUTH_CLIENT_ID='cid.apps.googleusercontent.com', GOOGLE_OAUTH_CLIENT_SECRET='sec',
    CALENDAR_OAUTH_REDIRECT_URI='http://localhost:5173/auth/calendar/callback')


def _user(name, role, tz='UTC'):
    u = User.objects.create_user(username=f'{name}@example.com', email=f'{name}@example.com', password='pw12345!')
    u.profile.role = role
    u.profile.timezone = tz
    u.profile.save()
    return u


class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass


def http_error(code, payload):
    return urllib.error.HTTPError('http://x', code, 'err', {}, io.BytesIO(json.dumps(payload).encode()))


class FakeGoogle:
    """Scripted urlopen: pops one queued response/exception per call and records the request."""
    def __init__(self, *queue):
        self.queue = list(queue)
        self.calls = []

    def __call__(self, req, timeout=None):
        body = json.loads(req.data.decode()) if (req.data and req.data[:1] in (b'{', b'[')) else req.data
        self.calls.append({'method': req.get_method(), 'url': req.full_url, 'body': body,
                           'auth': req.headers.get('Authorization')})
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResp(item)

    def calendar_calls(self, method=None):
        return [c for c in self.calls if 'googleapis.com/calendar' in c['url'] and (method is None or c['method'] == method)]


def event(status, url=None, event_id='evt1'):
    ev = {'id': event_id, 'conferenceData': {'createRequest': {'status': {'statusCode': status}}}}
    if url:
        ev['conferenceData']['entryPoints'] = [{'entryPointType': 'video', 'uri': url}]
        ev['hangoutLink'] = url
    return ev


def make_creds(user, access='acc-token', refresh='ref-token', expiry_delta=timedelta(hours=1)):
    return GoogleCalendarCredentials.objects.create(
        user=user, email=user.email, access_token_encrypted=encryption.encrypt_password(access),
        refresh_token_encrypted=encryption.encrypt_password(refresh),
        token_expiry=timezone.now() + expiry_delta, scopes=CAL_SCOPE, is_active=True)


def make_prospect(lq=None, name='Acme Corp'):
    p = Prospect.objects.create(
        company_name=name, country_head_office='IN', primary_industries='IT', company_structure='Parent',
        operational_status='Active', primary_offering_type='Products', official_website_url='https://a.test')
    if lq:
        lqual, _ = LeadQualification.objects.get_or_create(prospect=p)
        lqual.assigned_lq = lq
        lqual.save()
    return p


# ── OAuth / credential lifecycle ────────────────────────────────────────────────
@override_settings(**OAUTH_SETTINGS)
class CalendarOAuthTests(APITestCase):
    def setUp(self):
        self.lq = _user('lq1', 'LQ')
        self.lq2 = _user('lq2', 'LQ')
        self.mgr = _user('mgr', 'MANAGER')
        self.pre = _user('pre', 'PRE')
        self.client.force_authenticate(user=self.lq)

    def _state(self, user=None):
        url = self.client.get('/api/auth/google/calendar/url/').data
        return url['state']

    def test_requires_authentication_and_lq_role(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/auth/google/calendar/url/').status_code, 401)
        self.assertEqual(self.client.get('/api/auth/google/calendar/status/').status_code, 401)
        # PRE is strictly denied
        self.client.force_authenticate(user=self.pre)
        self.assertEqual(self.client.get('/api/auth/google/calendar/url/').status_code, 403)
        # Manager is allowed
        self.client.force_authenticate(user=self.mgr)
        self.assertEqual(self.client.get('/api/auth/google/calendar/url/').status_code, 200)

    def test_url_uses_unified_scopes_and_separate_redirect(self):
        r = self.client.get('/api/auth/google/calendar/url/')
        self.assertEqual(r.status_code, 200)
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(r.data['url']).query)
        self.assertIn(CAL_SCOPE, q['scope'][0])
        self.assertIn('mail.google.com', q['scope'][0])
        self.assertEqual(q['redirect_uri'], ['http://localhost:5173/auth/calendar/callback'])
        self.assertEqual(q['access_type'], ['offline'])

    def test_callback_stores_encrypted_tokens_and_leaks_nothing(self):
        state = self._state()
        tokens = {'access_token': 'ACCESS-SECRET', 'refresh_token': 'REFRESH-SECRET', 'expires_in': 3600, 'scope': CAL_SCOPE}
        with mock.patch.object(GoogleOAuthService, 'exchange_code_for_tokens', return_value=tokens):
            r = self.client.post('/api/auth/google/calendar/callback/', {'code': 'c', 'state': state}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertNotIn('ACCESS-SECRET', json.dumps(r.data))
        self.assertNotIn('REFRESH-SECRET', json.dumps(r.data))
        c = GoogleCalendarCredentials.objects.get(user=self.lq)
        self.assertNotIn('SECRET', c.access_token_encrypted + c.refresh_token_encrypted)
        self.assertEqual(encryption.decrypt_password(c.refresh_token_encrypted), 'REFRESH-SECRET')
        status_r = self.client.get('/api/auth/google/calendar/status/')
        self.assertTrue(status_r.data['is_connected'])
        self.assertNotIn('token', json.dumps(status_r.data, default=str).lower().replace('is_connected', ''))

    def test_gmail_credentials_synced_by_calendar_connect(self):
        gm = GoogleMailCredentials.objects.create(user=self.lq, email='m@x.com', access_token_encrypted='keep', is_active=True)
        state = self._state()
        with mock.patch.object(GoogleOAuthService, 'exchange_code_for_tokens',
                               return_value={'access_token': 'a', 'refresh_token': 'r', 'scope': CAL_SCOPE}):
            self.client.post('/api/auth/google/calendar/callback/', {'code': 'c', 'state': state}, format='json')
        gm.refresh_from_db()
        self.assertTrue(gm.is_active)

    def test_state_bound_to_user_and_single_use(self):
        state = self._state()
        tokens = {'access_token': 'a', 'refresh_token': 'r', 'scope': CAL_SCOPE}
        # Another user cannot redeem it
        self.client.force_authenticate(user=self.lq2)
        with mock.patch.object(GoogleOAuthService, 'exchange_code_for_tokens', return_value=tokens):
            r = self.client.post('/api/auth/google/calendar/callback/', {'code': 'c', 'state': state}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(GoogleCalendarCredentials.objects.filter(user=self.lq2).exists())
        # Owner can redeem once; replay is rejected
        self.client.force_authenticate(user=self.lq)
        with mock.patch.object(GoogleOAuthService, 'exchange_code_for_tokens', return_value=tokens):
            self.assertEqual(self.client.post('/api/auth/google/calendar/callback/', {'code': 'c', 'state': state}, format='json').status_code, 200)
            self.assertEqual(self.client.post('/api/auth/google/calendar/callback/', {'code': 'c', 'state': state}, format='json').status_code, 400)

    def test_tampered_gmail_and_expired_state_rejected(self):
        with mock.patch.object(GoogleOAuthService, 'exchange_code_for_tokens') as ex:
            r = self.client.post('/api/auth/google/calendar/callback/', {'code': 'c', 'state': 'forged:state'}, format='json')
            self.assertEqual(r.status_code, 400)
            ex.assert_not_called()
        # A Gmail-flow state (different salt) is not accepted by the Calendar flow
        from accounts.oauth_services import GmailOAuthService
        gmail_state = GmailOAuthService.generate_authorization_url(self.lq.id)[1]
        self.assertFalse(cal.GoogleCalendarOAuthService.verify_state(gmail_state, self.lq.id))
        state = self._state()
        with mock.patch.object(cal.GoogleCalendarOAuthService, 'STATE_MAX_AGE', -1):
            self.assertFalse(cal.GoogleCalendarOAuthService.verify_state(state, self.lq.id))

    def test_missing_calendar_scope_rejected(self):
        state = self._state()
        with mock.patch.object(GoogleOAuthService, 'exchange_code_for_tokens',
                               return_value={'access_token': 'a', 'refresh_token': 'r', 'scope': 'openid email'}):
            r = self.client.post('/api/auth/google/calendar/callback/', {'code': 'c', 'state': state}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(GoogleCalendarCredentials.objects.filter(user=self.lq).exists())

    def test_disconnect_removes_only_own_credentials(self):
        make_creds(self.lq)
        make_creds(self.lq2)
        with mock.patch.object(cal.GoogleCalendarOAuthService, 'revoke') as rv:
            r = self.client.post('/api/auth/google/calendar/disconnect/')
        self.assertEqual(r.status_code, 200)
        rv.assert_called_once()
        self.assertFalse(GoogleCalendarCredentials.objects.filter(user=self.lq).exists())
        self.assertTrue(GoogleCalendarCredentials.objects.filter(user=self.lq2).exists())

    def test_expired_access_token_is_refreshed_and_persisted(self):
        c = make_creds(self.lq, expiry_delta=timedelta(seconds=-5))
        fake = FakeGoogle({'access_token': 'NEW', 'expires_in': 3600})
        with mock.patch('accounts.calendar_services.urllib.request.urlopen', fake):
            token = cal.GoogleCalendarOAuthService.get_valid_access_token(c)
        self.assertEqual(token, 'NEW')
        c.refresh_from_db()
        self.assertEqual(encryption.decrypt_password(c.access_token_encrypted), 'NEW')
        self.assertGreater(c.token_expiry, timezone.now())

    def test_revoked_consent_deactivates_credentials(self):
        c = make_creds(self.lq, expiry_delta=timedelta(seconds=-5))
        fake = FakeGoogle(http_error(400, {'error': 'invalid_grant'}))
        with mock.patch('accounts.calendar_services.urllib.request.urlopen', fake):
            with self.assertRaises(cal.CalendarAuthError):
                cal.GoogleCalendarOAuthService.get_valid_access_token(c)
        c.refresh_from_db()
        self.assertFalse(c.is_active)
        self.assertFalse(self.client.get('/api/auth/google/calendar/status/').data['is_connected'])


# ── Meeting creation ──────────────────────────────────────────────────────────────
@override_settings(**OAUTH_SETTINGS)
class GoogleMeetMeetingTests(APITestCase):
    def setUp(self):
        self.lq = _user('lqm', 'LQ', tz='Asia/Kolkata')
        self.lq2 = _user('lqm2', 'LQ')
        self.pre = _user('prem', 'PRE')
        self.mgr = _user('mgrm', 'MANAGER')
        self.prospect = make_prospect(self.lq)
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect, contact_name='Jane', designation='CTO', official_email='jane@acme.test')
        self.creds = make_creds(self.lq, access='LQ1-TOKEN')
        self.client.force_authenticate(user=self.lq)
        patcher = mock.patch('accounts.calendar_services.time.sleep')
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def payload(self, **extra):
        d = {'prospect': self.prospect.id, 'prospect_contact': self.contact.id,
             'scheduled_datetime': '2026-11-01T04:30:00Z', 'agenda': 'Discuss rollout',
             'meeting_provider': 'GOOGLE_MEET', 'client_request_id': 'req-0001-abcdef'}
        d.update(extra)
        return d

    def post(self, fake, **extra):
        with mock.patch('accounts.calendar_services.urllib.request.urlopen', fake):
            return self.client.post('/api/meetings/', self.payload(**extra), format='json')

    # ── success ──
    def test_success_creates_real_event_and_persists_everything(self):
        fake = FakeGoogle(event('success', MEET_URL))
        r = self.post(fake)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(fake.calendar_calls('POST')), 1)
        call = fake.calendar_calls('POST')[0]
        self.assertIn('/calendars/primary/events', call['url'])
        self.assertIn('conferenceDataVersion=1', call['url'])
        self.assertIn('sendUpdates=all', call['url'])
        self.assertEqual(call['auth'], 'Bearer LQ1-TOKEN')  # the user's own token
        b = call['body']
        self.assertEqual(b['summary'], 'Acme Corp')
        self.assertEqual(b['description'], 'Discuss rollout')
        self.assertEqual(b['conferenceData']['createRequest']['conferenceSolutionKey'], {'type': 'hangoutsMeet'})
        self.assertTrue(b['conferenceData']['createRequest']['requestId'])
        self.assertEqual(b['attendees'], [{'email': 'jane@acme.test'}])
        # timezone conversion: 04:30Z == 10:00 Asia/Kolkata, 30-minute default duration
        self.assertEqual(b['start'], {'dateTime': '2026-11-01T10:00:00+05:30', 'timeZone': 'Asia/Kolkata'})
        self.assertEqual(b['end']['dateTime'], '2026-11-01T10:30:00+05:30')
        m = Meeting.objects.get()
        self.assertEqual(m.meeting_link, MEET_URL)
        self.assertEqual(m.meeting_provider, 'GOOGLE_MEET')
        self.assertEqual(m.google_event_id, 'evt1')
        self.assertEqual(m.conference_status, 'READY')
        self.assertEqual(m.google_calendar_owner, self.lq)
        self.assertEqual(m.prospect_contact, self.contact)
        self.assertEqual(m.agenda, 'Discuss rollout')
        self.assertEqual(r.data['meeting_link'], MEET_URL)
        self.assertNotIn('LQ1-TOKEN', json.dumps(r.data, default=str))

    def test_no_attendee_when_no_key_person_or_invalid_email(self):
        fake = FakeGoogle(event('success', MEET_URL))
        self.post(fake, prospect_contact=None)
        self.assertNotIn('attendees', fake.calendar_calls('POST')[0]['body'])
        self.assertIn('sendUpdates=none', fake.calendar_calls('POST')[0]['url'])
        self.contact.official_email = 'not-an-email'
        self.contact.save()
        Meeting.objects.all().delete()
        fake = FakeGoogle(event('success', MEET_URL))
        r = self.post(fake, client_request_id='req-0002-abcdef')
        self.assertEqual(r.status_code, 201)
        self.assertNotIn('attendees', fake.calendar_calls('POST')[0]['body'])

    # ── conference lifecycle ──
    def test_pending_then_success_via_bounded_polling(self):
        fake = FakeGoogle(event('pending'), event('pending'), event('success', MEET_URL))
        r = self.post(fake)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Meeting.objects.get().meeting_link, MEET_URL)
        self.assertEqual(len(fake.calendar_calls('GET')), 2)

    def test_still_pending_is_not_reported_as_ready_and_can_be_refreshed(self):
        fake = FakeGoogle(*([event('pending')] * (1 + cal.CONFERENCE_POLL_ATTEMPTS)))
        r = self.post(fake)
        self.assertEqual(r.status_code, 202, r.data)
        m = Meeting.objects.get()
        self.assertEqual(m.conference_status, 'PENDING')
        self.assertFalse(m.meeting_link)
        with mock.patch('accounts.calendar_services.urllib.request.urlopen', FakeGoogle(event('success', MEET_URL))):
            rr = self.client.post(f'/api/meetings/{m.id}/refresh-meet-link/')
        self.assertEqual(rr.status_code, 200, rr.data)
        m.refresh_from_db()
        self.assertEqual((m.conference_status, m.meeting_link), ('READY', MEET_URL))

    def test_failed_conference_cleans_up_event_and_creates_no_meeting(self):
        fake = FakeGoogle(event('failure'), {})  # insert -> failure ; DELETE -> {}
        r = self.post(fake)
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.data['code'], 'conference_failed')
        self.assertFalse(Meeting.objects.exists())
        self.assertEqual(len(fake.calendar_calls('DELETE')), 1)

    def test_google_api_error_is_reported_honestly(self):
        fake = FakeGoogle(http_error(500, {'error': {'message': 'Backend Error'}}))
        r = self.post(fake)
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.data['code'], 'calendar_api_error')
        self.assertFalse(Meeting.objects.exists())

    def test_revoked_or_missing_permission_asks_to_reconnect(self):
        fake = FakeGoogle(http_error(401, {'error': {'message': 'Invalid Credentials'}}))
        r = self.post(fake)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['code'], 'calendar_reauth_required')
        self.assertFalse(Meeting.objects.exists())
        self.creds.refresh_from_db()
        self.assertFalse(self.creds.is_active)

    def test_expired_token_refreshes_transparently_before_event_creation(self):
        self.creds.token_expiry = timezone.now() - timedelta(minutes=1)
        self.creds.save()
        fake = FakeGoogle({'access_token': 'FRESH', 'expires_in': 3600}, event('success', MEET_URL))
        r = self.post(fake)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(fake.calendar_calls('POST')[0]['auth'], 'Bearer FRESH')

    # ── connection / isolation ──
    def test_not_connected_returns_actionable_error(self):
        self.creds.delete()
        r = self.post(FakeGoogle())
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['code'], 'calendar_not_connected')
        self.assertFalse(Meeting.objects.exists())

    def test_never_uses_another_users_credentials(self):
        self.creds.delete()
        make_creds(self.lq2, access='OTHER-USERS-TOKEN')
        fake = FakeGoogle()
        r = self.post(fake)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(fake.calls, [])

    # ── duplicate protection ──
    def test_duplicate_submit_creates_one_event_and_one_meeting(self):
        fake = FakeGoogle(event('success', MEET_URL))
        first = self.post(fake)
        second = self.post(fake)  # queue empty: a second Google call would raise IndexError
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Meeting.objects.count(), 1)
        self.assertEqual(len(fake.calendar_calls('POST')), 1)

    def test_retry_after_local_failure_reuses_existing_google_event(self):
        # Google reports the deterministic event id already exists -> fetch, don't duplicate
        fake = FakeGoogle(http_error(409, {'error': {'message': 'identifier already exists'}}),
                          event('success', MEET_URL))
        r = self.post(fake)
        self.assertEqual(r.status_code, 201, r.data)
        ids = {json.dumps(c['body']['id']) for c in fake.calendar_calls('POST')}
        self.assertEqual(len(ids), 1)
        self.assertEqual(Meeting.objects.count(), 1)

    def test_same_request_id_is_deterministic_per_user(self):
        a = cal.deterministic_event_id(1, 'x')
        self.assertEqual(a, cal.deterministic_event_id(1, 'x'))
        self.assertNotEqual(a, cal.deterministic_event_id(2, 'x'))

    def test_client_request_id_required_for_meet(self):
        r = self.post(FakeGoogle(), client_request_id='')
        self.assertEqual(r.status_code, 400)

    # ── permissions ──
    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post('/api/meetings/', self.payload(), format='json').status_code, 401)

    def test_pre_cannot_create_meet(self):
        self.client.force_authenticate(user=self.pre)
        fake = FakeGoogle()
        self.assertEqual(self.post(fake).status_code, 403)
        self.assertEqual(fake.calls, [])
        self.assertFalse(Meeting.objects.exists())

    def test_lq_cannot_schedule_for_prospect_assigned_to_someone_else(self):
        other_prospect = make_prospect(self.lq2, name='Other Co')
        fake = FakeGoogle()
        r = self.post(fake, prospect=other_prospect.id, prospect_contact=None)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(fake.calls, [])

    def test_contact_from_another_prospect_rejected(self):
        other = make_prospect(self.lq, name='Third')
        stranger = ProspectContact.objects.create(prospect=other, contact_name='X', official_email='x@x.com')
        fake = FakeGoogle()
        r = self.post(fake, prospect_contact=stranger.id)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(fake.calls, [])

    def test_only_creator_can_refresh_meet_link(self):
        m = Meeting.objects.create(prospect=self.prospect, scheduled_datetime=timezone.now() + timedelta(days=1),
                                   meeting_provider='GOOGLE_MEET', google_event_id='e', google_calendar_owner=self.lq,
                                   conference_status='PENDING')
        self.client.force_authenticate(user=self.mgr)
        self.assertEqual(self.client.post(f'/api/meetings/{m.id}/refresh-meet-link/').status_code, 403)

    # ── manual path removed ──
    def test_manual_meeting_rejected_now_that_manual_calendar_removed(self):
        self.creds.delete()
        r = self.client.post('/api/meetings/', {
            'prospect': self.prospect.id, 'prospect_contact': self.contact.id,
            'scheduled_datetime': '2026-11-01T04:30:00Z', 'meeting_link': 'https://zoom.us/j/123',
            'agenda': 'Manual', 'meeting_provider': 'MANUAL'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data.get('code'), 'manual_calendar_removed')

    def test_client_cannot_create_manual_meeting(self):
        r = self.client.post('/api/meetings/', {
            'prospect': self.prospect.id, 'scheduled_datetime': '2026-11-01T04:30:00Z',
            'meeting_link': 'https://zoom.us/j/9', 'meeting_provider': 'MANUAL'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data.get('code'), 'manual_calendar_removed')

    def test_manual_meeting_rejected_across_roles(self):
        self.client.force_authenticate(user=self.mgr)
        r = self.client.post('/api/meetings/', {'prospect': self.prospect.id,
                                                'scheduled_datetime': '2026-11-01T04:30:00Z',
                                                'meeting_provider': 'MANUAL'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get('/api/meetings/').status_code, 200)

    def test_existing_manual_meetings_listed_with_link(self):
        Meeting.objects.create(prospect=self.prospect, scheduled_datetime=timezone.now() + timedelta(days=1),
                               meeting_link='https://old.example/m')
        r = self.client.get('/api/meetings/')
        self.assertEqual(r.status_code, 200)
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual(rows[0]['meeting_link'], 'https://old.example/m')
        self.assertEqual(rows[0]['meeting_provider'], 'MANUAL')
