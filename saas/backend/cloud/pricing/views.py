from decimal import Decimal

from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from cloud.accounts.permissions import IsPlatformOrReadOnlyStaff
from cloud.pricing.models import SERVICE_TYPES, PricingPlan, PricingTier


class TierSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingTier
        fields = ['id', 'up_to', 'unit_price', 'flat_fee']


class PlanSerializer(serializers.ModelSerializer):
    tiers = TierSerializer(many=True, required=False)
    tenant_count = serializers.IntegerField(source='tenants.count', read_only=True)
    examples = serializers.SerializerMethodField()

    class Meta:
        model = PricingPlan
        fields = ['id', 'name', 'code', 'description', 'is_active', 'is_public', 'is_default', 'sort_order',
                  'count_basis', 'service_types', 'count_method', 'tier_mode', 'base_fee', 'included_subscribers',
                  'minimum_charge', 'maximum_charge', 'prorate_first_period', 'collection_fee_percent',
                  'settlement_fee_flat', 'tiers', 'tenant_count', 'examples']

    def get_examples(self, obj):
        # What an ISP of a few sizes would pay -- shown on the sign-up page.
        return [{'subscribers': n, 'amount': obj.quote(n)['amount']} for n in (50, 200, 500, 1000)]

    def validate_service_types(self, v):
        types = [t.strip() for t in v.split(',') if t.strip()]
        bad = [t for t in types if t not in SERVICE_TYPES]
        if bad or not types:
            raise serializers.ValidationError(f'Choose from {", ".join(SERVICE_TYPES)}.')
        return ','.join(types)

    def validate_tiers(self, tiers):
        bounds = [t.get('up_to') for t in tiers]
        if bounds.count(None) > 1:
            raise serializers.ValidationError('Only the last tier can be unlimited.')
        finite = [b for b in bounds if b is not None]
        if len(set(finite)) != len(finite):
            raise serializers.ValidationError('Two tiers have the same upper bound.')
        if tiers and None not in bounds:
            raise serializers.ValidationError('Make the last tier unlimited (leave "up to" blank) so every count has a price.')
        return tiers

    def validate(self, data):
        mx, mn = data.get('maximum_charge'), data.get('minimum_charge', Decimal('0'))
        if mx is not None and mn and mx < mn:
            raise serializers.ValidationError({'maximum_charge': 'The cap is below the minimum charge.'})
        return data

    @transaction.atomic
    def create(self, data):
        tiers = data.pop('tiers', [])
        plan = PricingPlan.objects.create(**data)
        for t in tiers:
            PricingTier.objects.create(plan=plan, **t)
        return plan

    @transaction.atomic
    def update(self, plan, data):
        tiers = data.pop('tiers', None)
        plan = super().update(plan, data)
        if tiers is not None:
            plan.tiers.all().delete()
            for t in tiers:
                PricingTier.objects.create(plan=plan, **{k: v for k, v in t.items() if k != 'id'})
        return plan


class PlanListView(APIView):
    permission_classes = [IsPlatformOrReadOnlyStaff]

    def get(self, request):
        return Response(PlanSerializer(PricingPlan.objects.prefetch_related('tiers'), many=True).data)

    def post(self, request):
        s = PlanSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data, status=201)


class PlanDetailView(APIView):
    permission_classes = [IsPlatformOrReadOnlyStaff]

    def _get(self, pk):
        return PricingPlan.objects.filter(pk=pk).first()

    def patch(self, request, pk):
        plan = self._get(pk)
        if not plan:
            return Response(status=404)
        s = PlanSerializer(plan, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    def delete(self, request, pk):
        plan = self._get(pk)
        if not plan:
            return Response(status=404)
        if plan.tenants.exists():
            return Response({'error': 'ISPs are on this plan. Move them first, or just make the plan inactive.'}, status=409)
        plan.delete()
        return Response(status=204)


class QuoteView(APIView):
    """Price `count` subscribers on a saved plan, or on unsaved form values
    (the editor's live calculator)."""
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        count = max(0, int(request.data.get('count') or 0))
        if request.data.get('plan_id'):
            plan = PricingPlan.objects.filter(pk=request.data['plan_id'], is_active=True).first()
            if not plan or not (plan.is_public or (request.user and getattr(request.user, 'is_platform', False))):
                return Response(status=404)
            return Response(plan.quote(count))
        s = PlanSerializer(data={**request.data.get('plan', {}), 'name': 'x', 'code': 'quote-preview'})
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        tiers = [PricingTier(**t) for t in data.pop('tiers', [])]
        return Response(PricingPlan(**data).quote(count, tiers=tiers))
