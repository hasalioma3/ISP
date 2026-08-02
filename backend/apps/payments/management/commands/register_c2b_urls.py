from urllib.parse import urljoin

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.payments.services.mpesa_service import mpesa_service


class Command(BaseCommand):
    help = (
        "Register the C2B ValidationURL/ConfirmationURL with Safaricom for "
        "the configured MPESA_SHORTCODE. Required once before direct "
        "paybill payments will be delivered to this app at all; safe to "
        "re-run any time the domain or MPESA_C2B_SECRET changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--base-url',
            default=None,
            help=(
                "Public base URL to build the C2B endpoints from, e.g. "
                "https://portal.hasanet.net -- defaults to deriving it from "
                "MPESA_CALLBACK_URL if not given."
            ),
        )

    def handle(self, *args, **options):
        if not settings.MPESA_C2B_SECRET:
            raise CommandError(
                "MPESA_C2B_SECRET is not set -- refusing to register C2B "
                "URLs without it, since that secret is what protects the "
                "confirmation endpoint from being called by anyone else."
            )

        base_url = options['base_url']
        if not base_url:
            # MPESA_CALLBACK_URL looks like https://host/api/payments/callback/
            callback = settings.MPESA_CALLBACK_URL
            base_url = callback.split('/api/')[0]

        validation_url = urljoin(
            base_url + '/', f"api/payments/c2b/{settings.MPESA_C2B_SECRET}/validation/"
        )
        confirmation_url = urljoin(
            base_url + '/', f"api/payments/c2b/{settings.MPESA_C2B_SECRET}/confirmation/"
        )

        self.stdout.write(f"Registering against {settings.MPESA_BASE_URL} for shortcode {settings.MPESA_SHORTCODE}")
        self.stdout.write(f"  ValidationURL:   {validation_url}")
        self.stdout.write(f"  ConfirmationURL: {confirmation_url}")

        result = mpesa_service.register_c2b_urls(validation_url, confirmation_url)

        if result['success']:
            self.stdout.write(self.style.SUCCESS(f"Registered: {result['data']}"))
        else:
            raise CommandError(f"Registration failed: {result['error']}")
