from django.http import FileResponse
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.archive import service
from apps.archive.models import ArchiveRun, ArchiveSettings
from apps.audit.views import IsSuperadmin


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchiveSettings
        fields = ['enabled', 'months', 'datasets', 'hour', 'last_run_at', 'updated_at']
        read_only_fields = ['last_run_at', 'updated_at']

    def validate_months(self, v):
        if v < 1 or v > 120:
            raise serializers.ValidationError('Choose between 1 and 120 months.')
        return v

    def validate_hour(self, v):
        if v > 23:
            raise serializers.ValidationError('Hour must be 0-23.')
        return v

    def validate_datasets(self, v):
        keys = [k.strip() for k in (v or '').split(',') if k.strip()]
        bad = [k for k in keys if k not in service.DATASETS]
        if bad:
            raise serializers.ValidationError(f"Unknown dataset(s): {', '.join(bad)}")
        return ','.join(dict.fromkeys(keys))


class RunSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    file_exists = serializers.SerializerMethodField()

    class Meta:
        model = ArchiveRun
        fields = ['id', 'dataset', 'label', 'cutoff', 'status', 'rows', 'file_name', 'size_bytes', 'error',
                  'triggered_by', 'started_at', 'finished_at', 'restored_at', 'file_exists']

    def get_label(self, obj):
        return service.DATASETS.get(obj.dataset, (obj.dataset,))[0]

    def get_file_exists(self, obj):
        return bool(service.file_path(obj))


class ArchiveSettingsView(APIView):
    """GET/PUT the archive settings, plus the datasets on offer and how many
    rows each would archive with the current (or ?months=) cut-off."""
    permission_classes = [IsSuperadmin]

    def get(self, request):
        cfg = ArchiveSettings.load()
        try:
            months = max(1, int(request.query_params.get('months') or cfg.months))
        except ValueError:
            months = cfg.months
        return Response({**SettingsSerializer(cfg).data, 'preview': service.preview(months),
                         'available': [{'key': k, 'label': v[0]} for k, v in service.DATASETS.items()]})

    def put(self, request):
        ser = SettingsSerializer(ArchiveSettings.load(), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return self.get(request)

    patch = put


class ArchiveRunListView(APIView):
    permission_classes = [IsSuperadmin]

    def get(self, request):
        runs = ArchiveRun.objects.all()[:200]
        return Response(RunSerializer(runs, many=True).data)

    def post(self, request):
        """Archive now (in the background) with the saved settings."""
        from apps.archive.tasks import archive_now
        if not ArchiveSettings.load().dataset_list():
            return Response({'error': 'Choose at least one kind of data to archive first.'}, status=400)
        archive_now.delay(request.user.username)
        return Response({'queued': True}, status=status.HTTP_202_ACCEPTED)


class ArchiveRunDetailView(APIView):
    permission_classes = [IsSuperadmin]

    def get(self, request, pk):
        run = ArchiveRun.objects.filter(pk=pk).first()
        path = run and service.file_path(run)
        if not path:
            return Response({'error': 'Archive file not found'}, status=404)
        return FileResponse(open(path, 'rb'), as_attachment=True, filename=run.file_name.split('/')[-1])

    def post(self, request, pk):
        """Restore the file back into the database."""
        run = ArchiveRun.objects.filter(pk=pk).first()
        if not run:
            return Response({'error': 'Not found'}, status=404)
        try:
            n = service.restore(run)
        except FileNotFoundError as e:
            return Response({'error': str(e)}, status=404)
        return Response({'restored': n})

    def delete(self, request, pk):
        """Delete the archive file (the data is then gone for good)."""
        import os
        run = ArchiveRun.objects.filter(pk=pk).first()
        if not run:
            return Response(status=404)
        path = service.file_path(run)
        if path:
            os.remove(path)
        run.delete()
        return Response(status=204)
