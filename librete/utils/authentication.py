from allauth.headless.contrib.rest_framework.authentication import XSessionTokenAuthentication


class SessionTokenAuthentication(XSessionTokenAuthentication):
    """`X-Session-Token` auth that answers 401 (not 403) for missing or invalid tokens,
    so clients know they have to log in again."""

    allow_invalid_session_tokens = False
