from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.customers.models import Customer
from apps.customers.permissions import RoleAllowed
from apps.loyalty import services
from apps.loyalty.models import LoyaltySettings, LoyaltyTransaction


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltySettings
        exclude = ['id']
        read_only_fields = ['updated_at']

    def validate_kes_per_point(self, v):
        if v <= 0:
            raise serializers.ValidationError('Must be more than 0.')
        return v

    def validate_point_value_kes(self, v):
        if v < 0:
            raise serializers.ValidationError('Cannot be negative.')
        return v

    def validate_service_types(self, v):
        types = [t.strip() for t in (v or '').split(',') if t.strip()]
        bad = [t for t in types if t not in ('pppoe', 'hotspot', 'static')]
        if bad:
            raise serializers.ValidationError(f"Unknown service type(s): {', '.join(bad)}")
        return ','.join(dict.fromkeys(types))


class EntrySerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', default='', read_only=True)
    receipt = serializers.CharField(source='transaction.mpesa_receipt_number', default='', read_only=True)

    class Meta:
        model = LoyaltyTransaction
        fields = ['id', 'kind', 'points', 'balance_after', 'kes_value', 'description', 'receipt',
                  'created_by_username', 'created_at']


class LoyaltySettingsView(APIView):
    permission_classes = [RoleAllowed('admin')]

    def get(self, request):
        return Response(SettingsSerializer(LoyaltySettings.load()).data)

    def put(self, request):
        ser = SettingsSerializer(LoyaltySettings.load(), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    patch = put


class LoyaltyOverviewView(APIView):
    """Programme totals plus the member list (customers with any points
    activity), searchable and sorted by balance."""
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request):
        cfg = LoyaltySettings.load()
        month_start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        all_entries = LoyaltyTransaction.objects.all()
        outstanding = all_entries.aggregate(t=Sum('points'))['t'] or 0
        month = all_entries.filter(created_at__gte=month_start)
        stats = {
            'outstanding_points': outstanding,
            'liability_kes': str(services.value_of(outstanding, cfg)),
            'earned_this_month': month.filter(points__gt=0).aggregate(t=Sum('points'))['t'] or 0,
            'redeemed_this_month': -(month.filter(kind='redeem').aggregate(t=Sum('points'))['t'] or 0),
            'redeemed_kes_this_month': str(month.filter(kind='redeem').aggregate(t=Sum('kes_value'))['t'] or 0),
            'members': all_entries.values('customer_id').distinct().count(),
        }
        search = (request.query_params.get('search') or '').strip()
        members = Customer.objects.filter(loyalty_entries__isnull=False)
        if search:
            members = members.filter(Q(username__icontains=search) | Q(first_name__icontains=search)
                                     | Q(last_name__icontains=search) | Q(phone_number__icontains=search))
        members = members.annotate(
            points=Sum('loyalty_entries__points'), entries=Count('loyalty_entries'),
            earned=Sum('loyalty_entries__points', filter=Q(loyalty_entries__points__gt=0)),
        ).order_by('-points', 'username')[:200]
        rows = [{
            'customer_id': c.pk, 'username': c.username, 'name': c.get_full_name() or c.username,
            'phone': c.phone_number, 'service_type': c.service_type, 'points': c.points or 0,
            'earned': c.earned or 0, 'value_kes': str(services.value_of(c.points or 0, cfg)),
        } for c in members]
        return Response({'settings': SettingsSerializer(cfg).data, 'stats': stats, 'members': rows})


class CustomerLoyaltyView(APIView):
    """One customer's points: GET summary + history; POST {action: redeem |
    adjust, points, reason}."""
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request, customer_id):
        customer = get_object_or_404(Customer, pk=customer_id)
        entries = LoyaltyTransaction.objects.filter(customer=customer).select_related('transaction', 'created_by')[:200]
        return Response({**services.summary(customer), 'customer': customer.username,
                         'entries': EntrySerializer(entries, many=True).data})

    def post(self, request, customer_id):
        customer = get_object_or_404(Customer, pk=customer_id)
        action = request.data.get('action')
        try:
            if action == 'redeem':
                entry, new_balance = services.redeem(customer, request.data.get('points'), actor=request.user)
                return Response({'entry': EntrySerializer(entry).data, 'account_balance': str(new_balance)})
            if action == 'adjust':
                if not (request.user.is_superuser or request.user.role == 'admin'):
                    return Response({'error': 'Only admins can adjust points.'}, status=403)
                entry = services.adjust(customer, request.data.get('points'), request.data.get('reason'), request.user)
                return Response({'entry': EntrySerializer(entry).data})
        except services.LoyaltyError as e:
            return Response({'error': str(e)}, status=400)
        return Response({'error': 'Unknown action'}, status=400)


class MyLoyaltyView(APIView):
    """The signed-in customer's own points; POST {points} to redeem."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entries = LoyaltyTransaction.objects.filter(customer=request.user).select_related('transaction')[:50]
        return Response({**services.summary(request.user), 'entries': EntrySerializer(entries, many=True).data})

    def post(self, request):
        cfg = LoyaltySettings.load()
        if not cfg.allow_self_redeem:
            return Response({'error': 'Please contact us to redeem your points.'}, status=403)
        if request.user.service_type not in cfg.service_type_list():
            return Response({'error': 'The loyalty programme is not available on your account.'}, status=403)
        try:
            entry, new_balance = services.redeem(request.user, request.data.get('points'), actor=request.user)
        except services.LoyaltyError as e:
            return Response({'error': str(e)}, status=400)
        return Response({'entry': EntrySerializer(entry).data, 'account_balance': str(new_balance),
                         **services.summary(request.user, cfg)})
