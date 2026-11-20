import base64

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management import call_command
from py_vapid import Vapid

from librete.contrib.reminders.models import PushSubscription
from librete.tests.factories import PushSubscriptionFactory

URL = "/api/push/subscriptions/"


def browser_subscription(endpoint="https://fcm.googleapis.com/fcm/send/abc123", **keys):
    return {
        "endpoint": endpoint,
        "expirationTime": None,
        "keys": {"p256dh": "BPublicKey", "auth": "AuthSecret", **keys},
    }


@pytest.mark.django_db
def test_vapid_key(auth_client, settings):
    settings.VAPID_PUBLIC_KEY = "BPublic"
    response = auth_client.get("/api/push/vapid-key/")
    assert response.status_code == 200
    assert response.json() == {"public_key": "BPublic"}


@pytest.mark.django_db
def test_vapid_key_is_null_when_not_configured(auth_client, settings):
    settings.VAPID_PUBLIC_KEY = ""
    assert auth_client.get("/api/push/vapid-key/").json() == {"public_key": None}


@pytest.mark.django_db
def test_push_endpoints_require_authentication(api_client, user):
    subscription = PushSubscriptionFactory(user=user)
    assert api_client.get("/api/push/vapid-key/").status_code == 401
    assert api_client.post(URL, browser_subscription()).status_code == 401
    assert api_client.delete(f"{URL}{subscription.id}/").status_code == 401


@pytest.mark.django_db
def test_subscribe(auth_client, user):
    response = auth_client.post(
        URL, browser_subscription(), HTTP_USER_AGENT="Mozilla/5.0 " + "x" * 300
    )
    assert response.status_code == 201, response.json()
    subscription = PushSubscription.objects.get()
    assert response.json() == {
        "id": subscription.id,
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
        "created_at": response.json()["created_at"],
    }
    assert subscription.user == user
    assert (subscription.p256dh, subscription.auth) == ("BPublicKey", "AuthSecret")
    assert subscription.user_agent.startswith("Mozilla/5.0 ")
    assert len(subscription.user_agent) == 255
    assert subscription.last_used_at is None


@pytest.mark.django_db
def test_subscribing_again_updates_the_existing_subscription(auth_client, user):
    first = auth_client.post(URL, browser_subscription()).json()
    response = auth_client.post(URL, browser_subscription(auth="NewSecret"))
    assert response.status_code == 200
    assert response.json()["id"] == first["id"]
    assert PushSubscription.objects.get().auth == "NewSecret"


@pytest.mark.django_db
def test_endpoint_moves_to_the_current_user(client_for, user, other_user):
    theirs = PushSubscriptionFactory(user=other_user)
    response = client_for(user).post(URL, browser_subscription(endpoint=theirs.endpoint))
    assert response.status_code == 200
    assert response.json()["id"] == theirs.id
    theirs.refresh_from_db()
    assert theirs.user == user
    assert PushSubscription.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "data",
    [
        {},
        {"endpoint": "https://push.example.com/x"},
        {"endpoint": "https://push.example.com/x", "keys": {"p256dh": "k"}},
        {"endpoint": "https://push.example.com/x", "keys": {"p256dh": "", "auth": "a"}},
        browser_subscription(endpoint="not a url"),
        browser_subscription(endpoint="http://push.example.com/insecure"),
        browser_subscription(endpoint="https://push.example.com/" + "x" * 500),
    ],
)
def test_invalid_subscriptions_are_rejected(auth_client, data):
    assert auth_client.post(URL, data).status_code == 400
    assert not PushSubscription.objects.exists()


@pytest.mark.django_db
def test_unsubscribe(auth_client, user):
    subscription = PushSubscriptionFactory(user=user)
    assert auth_client.delete(f"{URL}{subscription.id}/").status_code == 204
    assert not PushSubscription.objects.exists()


@pytest.mark.django_db
def test_cannot_delete_or_list_other_users_subscriptions(auth_client, other_user):
    theirs = PushSubscriptionFactory(user=other_user)
    assert auth_client.delete(f"{URL}{theirs.id}/").status_code == 404
    assert auth_client.get(URL).status_code == 405
    assert auth_client.get(f"{URL}{theirs.id}/").status_code == 405
    assert PushSubscription.objects.filter(pk=theirs.pk).exists()


@pytest.mark.django_db
def test_subscriptions_are_deleted_with_the_user(user):
    PushSubscriptionFactory(user=user)
    user.delete()
    assert not PushSubscription.objects.exists()


def b64url_decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_generate_vapid_keys(capsys):
    call_command("generate_vapid_keys")
    lines = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines())
    public, private = lines["VAPID_PUBLIC_KEY"], lines["VAPID_PRIVATE_KEY"]
    assert "=" not in public + private
    assert "+" not in public + private and "/" not in public + private

    public_bytes = b64url_decode(public)
    assert len(public_bytes) == 65 and public_bytes[0] == 4  # uncompressed P-256 point
    assert len(b64url_decode(private)) == 32

    # pywebpush loads the private key from this format, and it matches the public key.
    vapid = Vapid.from_string(private)
    derived = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    assert derived == public_bytes
    assert isinstance(vapid.private_key, ec.EllipticCurvePrivateKey)
