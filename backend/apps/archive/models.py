from django.db import models


class ArchiveSettings(models.Model):
    """
    Singleton (pk=1). Rows older than `months` in the chosen datasets are
    written to a gzip'd JSON-lines file under BACKUP_DIR/archive/ and then
    removed from the live database, so the Pi's Postgres (and every page that
    scans these tables) stays small. Off until an admin turns it on. Money
    records (transactions, M-Pesa C2B payments, subscriptions, invoices) are
    deliberately not offered: KRA expects them kept and other rows point at
    them.
    """
    enabled = models.BooleanField(default=False)
    months = models.PositiveSmallIntegerField(default=12)
    datasets = models.CharField(max_length=200, default='usage_records,notification_logs,payment_requests')
    # Local hour (0-23) the nightly run happens in.
    hour = models.PositiveSmallIntegerField(default=2)
    last_run_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'archive_settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def dataset_list(self):
        from apps.archive.service import DATASETS
        return [d for d in (x.strip() for x in (self.datasets or '').split(',')) if d in DATASETS]


class ArchiveRun(models.Model):
    STATUS = [('running', 'Running'), ('done', 'Done'), ('failed', 'Failed'), ('restored', 'Restored')]

    dataset = models.CharField(max_length=40)
    cutoff = models.DateTimeField(help_text='Rows created before this were archived')
    status = models.CharField(max_length=10, choices=STATUS, default='running')
    rows = models.PositiveIntegerField(default=0)
    file_name = models.CharField(max_length=255, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    error = models.TextField(blank=True)
    triggered_by = models.CharField(max_length=150, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    restored_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'archive_runs'
        ordering = ['-started_at']
