from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Make a backup right now, in this process (no Celery needed), and upload it if Drive is connected.'

    def add_arguments(self, parser):
        parser.add_argument('--no-upload', action='store_true')

    def handle(self, no_upload=False, **opts):
        from apps.backups import runner
        from apps.backups.models import Backup, BackupSettings
        backup = Backup.objects.create(kind='manual')
        self.stdout.write('Backing up...')
        runner.run(backup)
        if backup.status == 'failed':
            raise CommandError(backup.error)
        for w in backup.warnings:
            self.stdout.write(self.style.WARNING(w))
        self.stdout.write(self.style.SUCCESS(f'{runner.path_of(backup)} ({backup.size / 1024 ** 2:.1f} MB)'))
        cfg = BackupSettings.load()
        if not no_upload and cfg.gdrive_enabled and cfg.gdrive_refresh_token:
            runner.upload(backup)
            self.stdout.write(f'Google Drive: {backup.get_remote_status_display()} {backup.remote_error}')
        runner.prune()
