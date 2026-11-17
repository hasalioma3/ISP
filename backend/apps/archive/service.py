"""
Archive old rows to compressed files, then delete them from the database.

Each dataset is written in batches to
  BACKUP_DIR/archive/<dataset>/<dataset>_before_<YYYYMMDD>_<run id>.jsonl.gz
one Django-serialized object per line, so `restore()` can load it back with
the stock deserializer. A batch is deleted only after it has been written and
flushed, so a crash mid-run loses nothing: the next run starts again from the
oldest remaining row (and a re-archived row is harmless -- restore skips
primary keys that already exist).

Deletes use QuerySet._raw_delete: no per-row signals, so the audit log
doesn't get one entry per archived row (the ArchiveRun is the record), and
no cascade collection -- safe because each dataset deletes its own
dependents explicitly (payment callbacks before their payment requests).
"""
import gzip
import json
import logging
import os
from datetime import timedelta

from django.apps import apps as django_apps
from django.conf import settings
from django.core import serializers
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger('apps.archive')

BATCH = 2000

# key -> (label, model, date field, extra filter, dependents [(model, fk field)])
DATASETS = {
    'usage_records': ('Data usage records', 'billing.UsageRecord', 'created_at', {}, []),
    'notification_logs': ('Notification log (SMS/WhatsApp/email sent)', 'notifications.NotificationLog', 'created_at', {}, []),
    'payment_requests': ('STK push requests and callbacks (finished ones)', 'payments.PaymentRequest', 'created_at',
                         {'status__in': ['completed', 'failed', 'cancelled', 'timeout']},
                         [('payments.PaymentCallback', 'payment_request')]),
    'audit_logs': ('Audit log', 'audit.AuditLog', 'created_at', {}, []),
    'used_vouchers': ('Used/expired vouchers', 'billing.Voucher', 'created_at', {'status__in': ['used', 'expired']}, []),
}


def archive_dir():
    path = os.path.join(settings.BACKUP_DIR, 'archive')
    os.makedirs(path, exist_ok=True)
    return path


def _queryset(key, cutoff):
    _, model_label, field, extra, _ = DATASETS[key]
    model = django_apps.get_model(model_label)
    fields = {f.name for f in model._meta.get_fields()}
    extra = {k: v for k, v in extra.items() if k.split('__')[0] in fields}
    return model.objects.filter(**{f'{field}__lt': cutoff}, **extra).order_by('pk')


def preview(months):
    cutoff = timezone.now() - timedelta(days=30 * months)
    out = []
    for key, (label, *_rest) in DATASETS.items():
        try:
            count = _queryset(key, cutoff).count()
        except LookupError:
            continue
        out.append({'key': key, 'label': label, 'rows': count})
    return {'cutoff': cutoff, 'datasets': out}


def archive_dataset(key, months, triggered_by=''):
    from apps.archive.models import ArchiveRun
    cutoff = timezone.now() - timedelta(days=30 * months)
    run = ArchiveRun.objects.create(dataset=key, cutoff=cutoff, triggered_by=triggered_by)
    folder = os.path.join(archive_dir(), key)
    os.makedirs(folder, exist_ok=True)
    name = f'{key}_before_{timezone.localtime(cutoff):%Y%m%d}_{run.pk}.jsonl.gz'
    path = os.path.join(folder, name)
    total = 0
    deps = DATASETS[key][4]
    try:
        with gzip.open(path, 'wt', encoding='utf-8') as fh:
            while True:
                batch = list(_queryset(key, cutoff)[:BATCH])
                if not batch:
                    break
                ids = [o.pk for o in batch]
                for obj in serializers.serialize('python', batch):
                    fh.write(json.dumps(obj, default=str) + '\n')
                dep_qs = []
                for dep_label, fk in deps:
                    dep_model = django_apps.get_model(dep_label)
                    qs = dep_model.objects.filter(**{f'{fk}_id__in': ids})
                    for obj in serializers.serialize('python', qs):
                        fh.write(json.dumps(obj, default=str) + '\n')
                    dep_qs.append(qs)
                fh.flush()
                with transaction.atomic():
                    for qs in dep_qs:
                        qs._raw_delete(qs.db)
                    qs = _queryset(key, cutoff).model.objects.filter(pk__in=ids)
                    qs._raw_delete(qs.db)
                total += len(ids)
        run.status = 'done'
    except Exception as e:  # keep what was written; the rows not deleted stay live
        logger.exception('Archiving %s failed', key)
        run.status, run.error = 'failed', str(e)[:2000]
    run.rows = total
    run.finished_at = timezone.now()
    if total:
        run.file_name = os.path.relpath(path, archive_dir())
        run.size_bytes = os.path.getsize(path)
    else:
        try:
            os.remove(path)
        except OSError:
            pass
    run.save()
    return run


def run_all(triggered_by='schedule', force=False):
    from apps.archive.models import ArchiveSettings
    cfg = ArchiveSettings.load()
    if not force and not cfg.enabled:
        return []
    runs = [archive_dataset(key, max(1, cfg.months), triggered_by) for key in cfg.dataset_list()]
    cfg.last_run_at = timezone.now()
    cfg.save(update_fields=['last_run_at'])
    return runs


def file_path(run):
    base = os.path.realpath(archive_dir())
    path = os.path.realpath(os.path.join(base, run.file_name))
    if not run.file_name or not path.startswith(base + os.sep) or not os.path.isfile(path):
        return None
    return path


def restore(run):
    """Load an archive file back into the database; rows whose primary key
    already exists are left as they are. -> number of rows restored."""
    path = file_path(run)
    if not path:
        raise FileNotFoundError('The archive file is missing')
    restored = 0
    with gzip.open(path, 'rt', encoding='utf-8') as fh, transaction.atomic():
        buffer = []

        def flush():
            nonlocal restored
            for obj in serializers.deserialize('python', buffer, ignorenonexistent=True):
                model = type(obj.object)
                if not model.objects.filter(pk=obj.object.pk).exists():
                    model.objects.bulk_create([obj.object])
                    restored += 1
            buffer.clear()

        for line in fh:
            if line.strip():
                buffer.append(json.loads(line))
            if len(buffer) >= 500:
                flush()
        flush()
    run.status, run.restored_at = 'restored', timezone.now()
    run.save(update_fields=['status', 'restored_at'])
    return restored
