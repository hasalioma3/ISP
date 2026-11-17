"""
Self-signed TLS certificate for the ISP instances' nginx, written to the
shared certs volume (SAAS_DATA_DIR/certs) as selfsigned.crt/.key -- the
names the ISP app's nginx config expects. Replace them with a real
certificate (same names) for production; this never overwrites existing ones.
"""
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--dir', default=str(settings.SAAS_DATA_DIR / 'certs'))
        parser.add_argument('--host', default='localhost')

    def handle(self, *args, dir, host, **opts):
        from pathlib import Path
        out = Path(dir)
        out.mkdir(parents=True, exist_ok=True)
        crt, key = out / 'selfsigned.crt', out / 'selfsigned.key'
        if crt.exists() and key.exists():
            self.stdout.write('Certificates already present')
            return
        pk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(pk.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
                .not_valid_after(now + timedelta(days=3650))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(host), x509.DNSName('localhost')]), critical=False)
                .sign(pk, hashes.SHA256()))
        key.write_bytes(pk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                         serialization.NoEncryption()))
        crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key.chmod(0o644)  # read by nginx running as a different user in another container
        self.stdout.write(self.style.SUCCESS(f'Wrote {crt} and {key}'))
