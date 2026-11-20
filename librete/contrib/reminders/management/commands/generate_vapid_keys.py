import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_vapid_keys():
    """Return `(public_key, private_key)` as unpadded base64url strings.

    The public key is the uncompressed P-256 point (65 bytes), as browsers expect for
    `applicationServerKey`; the private key is the raw 32-byte scalar.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    public = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    private = private_key.private_numbers().private_value.to_bytes(32, "big")
    return b64url(public), b64url(private)


class Command(BaseCommand):
    help = "Generate a VAPID key pair for Web Push, printed as environment variables."

    def handle(self, *args, **options):
        public, private = generate_vapid_keys()
        self.stdout.write(f"VAPID_PUBLIC_KEY={public}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={private}")
