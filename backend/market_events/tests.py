from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import UserProfile
from .models import MarketEvent


def make_user(username, role=None, is_superuser=False):
    """Helper to create a user with an optional UserProfile role."""
    user = User.objects.create_user(
        username=username,
        password='testpass123',
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )
    if role:
        # The post_save signal on User already created a UserProfile.
        # Update the existing profile instead of creating a duplicate.
        user.profile.role = role
        user.profile.save()
    return user



def make_event(title='Test Event', country='US'):
    """Helper to create a MarketEvent for testing."""
    return MarketEvent.objects.create(
        event_title=title,
        host_country=country,
        start_date='2026-01-01',
        end_date='2026-01-03',
        created_by='test',
    )


def auth_client(user):
    """Return an APIClient authenticated as the given user."""
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


LIST_URL = '/api/market-events/'


def detail_url(pk):
    return f'/api/market-events/{pk}/'


class MarketEventPREPermissionTests(TestCase):
    """PRE users can perform full CRUD on market events."""

    def setUp(self):
        self.pre_user = make_user('pre_user', role='PRE')
        self.client = auth_client(self.pre_user)
        self.event = make_event()

    def test_list_returns_200(self):
        res = self.client.get(LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_detail_returns_200(self):
        res = self.client.get(detail_url(self.event.pk))
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_create_returns_201(self):
        payload = {
            'event_title': 'New Event',
            'host_country': 'Germany',
            'start_date': '2026-03-01',
            'end_date': '2026-03-03',
        }
        res = self.client.post(LIST_URL, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_update_returns_200(self):
        payload = {
            'event_title': 'Updated Event',
            'host_country': 'France',
            'start_date': '2026-04-01',
            'end_date': '2026-04-05',
        }
        res = self.client.put(detail_url(self.event.pk), payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_partial_update_returns_200(self):
        res = self.client.patch(
            detail_url(self.event.pk),
            {'event_title': 'Patched Event'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_delete_returns_204(self):
        res = self.client.delete(detail_url(self.event.pk))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)


class MarketEventLQPermissionTests(TestCase):
    """LQ users can read but not mutate market events."""

    def setUp(self):
        self.lq_user = make_user('lq_user', role='LQ')
        self.client = auth_client(self.lq_user)
        self.event = make_event()

    def test_list_returns_200(self):
        res = self.client.get(LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_detail_returns_200(self):
        res = self.client.get(detail_url(self.event.pk))
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_create_returns_403(self):
        payload = {
            'event_title': 'LQ Should Fail',
            'host_country': 'Spain',
            'start_date': '2026-05-01',
            'end_date': '2026-05-02',
        }
        res = self.client.post(LIST_URL, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_returns_403(self):
        payload = {
            'event_title': 'LQ Put Fail',
            'host_country': 'Italy',
            'start_date': '2026-05-01',
            'end_date': '2026-05-03',
        }
        res = self.client.put(detail_url(self.event.pk), payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_partial_update_returns_403(self):
        res = self.client.patch(
            detail_url(self.event.pk),
            {'event_title': 'LQ Patch Fail'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_returns_403(self):
        res = self.client.delete(detail_url(self.event.pk))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class MarketEventSuperuserPermissionTests(TestCase):
    """Superusers have full access to market events."""

    def setUp(self):
        self.superuser = make_user('admin_user', is_superuser=True)
        self.client = auth_client(self.superuser)
        self.event = make_event()

    def test_list_returns_200(self):
        res = self.client.get(LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_detail_returns_200(self):
        res = self.client.get(detail_url(self.event.pk))
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_create_returns_201(self):
        payload = {
            'event_title': 'Admin Event',
            'host_country': 'Japan',
            'start_date': '2026-06-01',
            'end_date': '2026-06-02',
        }
        res = self.client.post(LIST_URL, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_delete_returns_204(self):
        res = self.client.delete(detail_url(self.event.pk))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)


class MarketEventUnauthenticatedTests(TestCase):
    """Unauthenticated requests are always denied."""

    def setUp(self):
        self.event = make_event()
        self.client = APIClient()  # no credentials

    def test_list_returns_401(self):
        res = self.client.get(LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_detail_returns_401(self):
        res = self.client.get(detail_url(self.event.pk))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
