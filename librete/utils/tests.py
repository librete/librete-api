from datetime import timedelta

from django.utils import timezone

from oauth2_provider.models import Application, AccessToken


def get_authorization_header(user):
    app = create_application(user)
    token = create_access_token(user, app)
    return create_authorization_header(token)


def create_application(user,
                       client_type=Application.CLIENT_CONFIDENTIAL,
                       grant_type=Application.GRANT_PASSWORD,
                       recirect_uris='https://www.example.com/',
                       name='Test Application'):
    return Application.objects.create(
        client_type=client_type,
        authorization_grant_type=grant_type,
        redirect_uris=recirect_uris,
        name=name,
        user=user
    )


def create_access_token(user,
                        application,
                        scope='read write',
                        expires=7200,
                        token='secret-access-token'):
    return AccessToken.objects.create(
        user=user,
        scope=scope,
        expires=timezone.now() + timedelta(seconds=expires),
        token=token,
        application=application
    )


def create_authorization_header(token):
    return 'Bearer {0}'.format(token)


def format_datetime(date_time_object):
    return date_time_object.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
