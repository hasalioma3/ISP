from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from apps.audit.models import AuditLog


class IsSuperadmin(BasePermission):
    """The audit log is for superadmins only -- not even the 'admin' role."""
    message = 'Only a superadmin can view the logs.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class AuditLogSerializer(serializers.ModelSerializer):
    action_label = serializers.CharField(source='get_action_display')
    source_label = serializers.CharField(source='get_source_display')

    class Meta:
        model = AuditLog
        fields = ['id', 'created_at', 'actor', 'actor_username', 'actor_role', 'source', 'source_label', 'action',
                  'action_label', 'model', 'object_id', 'object_repr', 'changes', 'ip_address', 'user_agent',
                  'method', 'path', 'status_code', 'request_id']


class Pager(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


def _day(value, end=False):
    try:
        d = datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None
    dt = timezone.make_aware(datetime.combine(d, time.min))
    return dt + timedelta(days=1) if end else dt


def filtered(request):
    p = request.query_params
    qs = AuditLog.objects.all()
    start, end = _day(p.get('start_date')), _day(p.get('end_date'), end=True)
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lt=end)
    for param, field in (('action', 'action'), ('model', 'model'), ('source', 'source'),
                         ('request_id', 'request_id'), ('object_id', 'object_id')):
        if p.get(param):
            qs = qs.filter(**{field: p[param]})
    if p.get('actor'):
        qs = qs.filter(actor_username__iexact=p['actor'])
    if p.get('hide_requests') in ('1', 'true'):
        qs = qs.exclude(action='request')
    if p.get('search'):
        s = p['search'].strip()
        qs = qs.filter(Q(object_repr__icontains=s) | Q(actor_username__icontains=s) | Q(path__icontains=s)
                       | Q(ip_address__icontains=s) | Q(object_id=s))
    return qs


class AuditLogView(APIView):
    """
    GET /api/audit/logs/ -- filtered, paged audit log. Filters: start_date,
    end_date (YYYY-MM-DD, Nairobi), action, model, source, actor, search,
    request_id, object_id, hide_requests. ?export=csv|xlsx|pdf downloads the
    filtered rows (up to 20,000).
    """
    permission_classes = [IsSuperadmin]

    def get(self, request):
        from apps.analytics.exports import Section, export_format, export_response
        qs = filtered(request)
        fmt = export_format(request)
        if fmt:
            rows = []
            for log in qs[:20000]:
                rows.append([
                    timezone.localtime(log.created_at).strftime('%Y-%m-%d %H:%M:%S'), log.actor_username or 'system',
                    log.actor_role, log.get_action_display(), log.model, log.object_repr, _changes_text(log),
                    log.ip_address or '', log.get_source_display(),
                ])
            return export_response(
                fmt, filename=f"audit_log_{timezone.localdate():%Y%m%d}", title='Audit log',
                subtitle=_subtitle(request),
                sections=Section(['Time', 'By', 'Role', 'Action', 'Record type', 'Record', 'Changes', 'IP', 'Source'], rows),
            )
        pager = Pager()
        page = pager.paginate_queryset(qs, request, view=self)
        return pager.get_paginated_response(AuditLogSerializer(page, many=True).data)


class AuditFacetsView(APIView):
    """Values for the Logs page filters, plus counts for the period."""
    permission_classes = [IsSuperadmin]

    def get(self, request):
        qs = filtered(request)
        return Response({
            'actions': [{'value': v, 'label': l} for v, l in AuditLog.ACTIONS],
            'sources': [{'value': v, 'label': l} for v, l in AuditLog.SOURCES],
            'models': sorted(AuditLog.objects.exclude(model='').values_list('model', flat=True).distinct()),
            'actors': sorted(AuditLog.objects.exclude(actor_username='').values_list('actor_username', flat=True).distinct()),
            'counts': {r['action']: r['n'] for r in qs.values('action').annotate(n=Count('id'))},
            'total': qs.count(),
        })


def _subtitle(request):
    p = request.query_params
    bits = [f"{p.get('start_date') or 'start'} to {p.get('end_date') or 'today'}"]
    bits += [f'{k}: {p[k]}' for k in ('action', 'model', 'actor', 'search') if p.get(k)]
    return ' · '.join(bits)


def _changes_text(log):
    c = log.changes or {}
    if log.action == 'update':
        return '; '.join(f'{k}: {v[0]} → {v[1]}' if isinstance(v, list) and len(v) == 2 else f'{k}: {v}'
                         for k, v in c.items())[:1000]
    if log.action == 'request':
        return f'{log.status_code or ""} {c.get("body", "")}'[:1000]
    return ', '.join(f'{k}={v}' for k, v in c.items())[:1000]
