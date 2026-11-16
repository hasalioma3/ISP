from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Pre-flight checks for running on this host (routers reachable, M-Pesa, WhatsApp, backups).'

    def add_arguments(self, parser):
        parser.add_argument('--skip-routers', action='store_true')

    def handle(self, skip_routers=False, **opts):
        from apps.backups.preflight import run_checks
        result = run_checks(skip_routers=skip_routers)
        for c in result['checks']:
            mark = '✅' if c['ok'] else ('⚠️ ' if c['level'] == 'warn' else '❌')
            self.stdout.write(f"{mark} {c['name']}{(' -- ' + c['detail']) if c['detail'] else ''}")
        if not result['ok']:
            raise SystemExit(1)
