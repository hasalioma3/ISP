"""
Restore a backup archive onto this server:

    docker compose stop celery_worker celery_beat        # nothing writing meanwhile
    docker compose cp isp-backup-....tar.gz.enc backend:/backups/
    docker compose exec backend python manage.py restore_backup /backups/isp-backup-....tar.gz.enc
    docker compose exec backend python manage.py migrate
    docker compose up -d

Restores the database (replacing what's there) and media files. Router
configs, the env file and the WhatsApp login are extracted next to the
archive for you to use by hand: they're applied to other machines (the
routers, the host's .env.prod, the whatsapp volume), not to this
database. The passphrase comes from --passphrase or BACKUP_PASSPHRASE.
"""
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _safe_extract(tar, dest):
    dest = Path(dest).resolve()
    for m in tar.getmembers():
        target = (dest / m.name).resolve()
        if not str(target).startswith(str(dest)) or m.issym() or m.islnk() or m.isdev():
            raise CommandError(f'Refusing unsafe path in archive: {m.name}')
    tar.extractall(dest)


class Command(BaseCommand):
    help = 'Restore the database and media from a backup archive (.tar.gz or .tar.gz.enc).'

    def add_arguments(self, parser):
        parser.add_argument('archive')
        parser.add_argument('--passphrase', default=os.environ.get('BACKUP_PASSPHRASE', ''))
        parser.add_argument('--skip-db', action='store_true')
        parser.add_argument('--skip-media', action='store_true')
        parser.add_argument('--yes', action='store_true', help="Don't ask before replacing the database")

    def handle(self, archive, passphrase, skip_db, skip_media, yes, **opts):
        from apps.backups.crypto import DecryptionError, decrypt_file, is_encrypted
        src = Path(archive)
        if not src.exists():
            raise CommandError(f'{src} not found')
        work = Path(tempfile.mkdtemp(prefix='restore-', dir=src.parent))
        try:
            plain = src
            if is_encrypted(src):
                if not passphrase:
                    raise CommandError('This backup is encrypted: pass --passphrase or set BACKUP_PASSPHRASE')
                plain = work / 'archive.tar.gz'
                self.stdout.write('Decrypting...')
                try:
                    decrypt_file(src, plain, passphrase)
                except DecryptionError as e:
                    raise CommandError(str(e))
            out = work / 'contents'
            out.mkdir()
            with tarfile.open(plain, 'r:gz') as tar:
                _safe_extract(tar, out)
            if plain != src:
                plain.unlink()
            manifest = json.loads((out / 'manifest.json').read_text())
            counts = manifest.get('contents', {}).get('counts', {})
            self.stdout.write(f"Backup from {manifest['created_at']} ({manifest.get('tenant')}): {counts}")

            if not skip_db:
                if not yes and input('Replace this server\'s database with the backup? [y/N] ').lower() != 'y':
                    raise CommandError('Cancelled')
                self._restore_db(out / 'database')
            if not skip_media and (out / 'media').is_dir():
                media = Path(settings.MEDIA_ROOT)
                media.mkdir(parents=True, exist_ok=True)
                shutil.copytree(out / 'media', media, dirs_exist_ok=True)
                self.stdout.write(self.style.SUCCESS(f'Media restored to {media}'))

            keep = src.parent / f'{src.name.split(".tar")[0]}-extracted'
            extras = [p for p in ('routers', 'secrets') if (out / p).exists()]
            if extras:
                shutil.rmtree(keep, ignore_errors=True)
                keep.mkdir()
                for p in extras:
                    shutil.move(str(out / p), str(keep / p))
                self.stdout.write(f'Router configs / secrets extracted to {keep} -- copy what you need, then '
                                  'DELETE that folder (it holds passwords).')
            self.stdout.write(self.style.SUCCESS('Done. Now run: python manage.py migrate'))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _restore_db(self, folder):
        db = settings.DATABASES['default']
        if (folder / 'database.dump').exists():
            if 'postgresql' not in db['ENGINE']:
                raise CommandError('The backup is a PostgreSQL dump but this server uses SQLite')
            env = {**os.environ, 'PGPASSWORD': db.get('PASSWORD') or ''}
            cmd = ['pg_restore', '--clean', '--if-exists', '--no-owner', '--no-privileges', '--no-password',
                   '-h', db.get('HOST') or 'localhost', '-p', str(db.get('PORT') or 5432), '-U', db.get('USER') or '',
                   '-d', db['NAME'], str(folder / 'database.dump')]
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
            # pg_restore exits 1 for harmless warnings (e.g. extension comments); show them but only fail on errors.
            errors = [l for l in proc.stderr.splitlines() if 'error' in l.lower() and 'does not exist' not in l]
            if proc.returncode != 0 and errors:
                raise CommandError('pg_restore failed:\n' + '\n'.join(errors[:20]))
            self.stdout.write(self.style.SUCCESS('Database restored'))
        elif (folder / 'database.sqlite3').exists():
            from django.db import connection
            connection.close()
            shutil.copy2(folder / 'database.sqlite3', db['NAME'])
            self.stdout.write(self.style.SUCCESS('Database restored'))
        else:
            raise CommandError('No database in this archive')
