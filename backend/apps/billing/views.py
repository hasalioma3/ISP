from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from apps.billing.models import BillingPlan, Subscription, Transaction, UsageRecord
from apps.billing.serializers import (
    BillingPlanSerializer, SubscriptionSerializer,
    TransactionSerializer, UsageRecordSerializer
)
from apps.customers.permissions import RoleAllowed


class BillingPlanViewSet(viewsets.ModelViewSet):
    """
    Billing plans. List/retrieve are public (the captive portal and
    customer app need to show plans to unauthenticated users) and only ever
    return active plans for non-staff callers. Create/update/delete are
    admin-only.
    """
    serializer_class = BillingPlanSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [RoleAllowed('admin')()]

    def get_queryset(self):
        user = self.request.user
        if user and user.is_authenticated and user.is_staff:
            return BillingPlan.objects.all()
        return BillingPlan.objects.filter(is_active=True)

    @action(detail=False, methods=['get'], url_path='csv-template')
    def csv_template(self, request):
        """Downloadable CSV template for bulk-importing billing plans."""
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="billing_plans_template.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'name', 'service_type', 'price', 'duration_value', 'duration_unit',
            'download_speed', 'upload_speed', 'data_limit_gb', 'mikrotik_profile',
            'description', 'is_active',
        ])
        writer.writerow([
            'Home 10Mbps', 'pppoe', '2000', '30', 'days',
            '10', '10', '', 'home-10mb',
            'Standard home package', 'true',
        ])
        return response

    @action(detail=False, methods=['post'], url_path='import-csv')
    def import_csv(self, request):
        """
        Bulk-create billing plans from an uploaded CSV (see csv_template for
        the expected columns). service_type must be one of pppoe/hotspot/
        static; data_limit_gb and is_active are optional (blank = unlimited
        / active). Every row is validated independently -- one bad row
        doesn't block the rest.
        """
        import csv
        import io

        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({'error': 'file is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            decoded = csv_file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response({'error': 'File must be UTF-8 encoded CSV'}, status=status.HTTP_400_BAD_REQUEST)

        reader = csv.DictReader(io.StringIO(decoded))
        required_cols = {'name', 'service_type', 'price', 'download_speed', 'upload_speed', 'mikrotik_profile'}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            missing = required_cols - set(reader.fieldnames or [])
            return Response(
                {'error': f'CSV is missing required column(s): {", ".join(sorted(missing))}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        valid_service_types = {choice[0] for choice in BillingPlan.SERVICE_TYPE_CHOICES}
        created, errors = [], []

        for i, row in enumerate(reader, start=2):  # row 1 is the header
            name = (row.get('name') or '').strip()
            service_type = (row.get('service_type') or '').strip().lower()
            mikrotik_profile = (row.get('mikrotik_profile') or '').strip()

            if not name or not mikrotik_profile:
                errors.append({'row': i, 'name': name, 'error': 'name and mikrotik_profile are required'})
                continue
            if service_type not in valid_service_types:
                errors.append({'row': i, 'name': name, 'error': f'service_type must be one of {", ".join(sorted(valid_service_types))}'})
                continue

            try:
                price = float((row.get('price') or '').strip())
                download_speed = int((row.get('download_speed') or '').strip())
                upload_speed = int((row.get('upload_speed') or '').strip())
            except ValueError:
                errors.append({'row': i, 'name': name, 'error': 'price/download_speed/upload_speed must be numeric'})
                continue

            data_limit_raw = (row.get('data_limit_gb') or '').strip()
            data_limit_gb = None
            if data_limit_raw:
                try:
                    data_limit_gb = int(data_limit_raw)
                except ValueError:
                    errors.append({'row': i, 'name': name, 'error': 'data_limit_gb must be a whole number or blank'})
                    continue

            duration_unit = (row.get('duration_unit') or 'days').strip().lower()
            if duration_unit not in {c[0] for c in BillingPlan.DURATION_UNIT_CHOICES}:
                errors.append({'row': i, 'name': name, 'error': 'duration_unit must be one of minutes/hours/days/months'})
                continue
            duration_raw = (row.get('duration_value') or '').strip()
            try:
                duration_value = int(duration_raw) if duration_raw else 30
            except ValueError:
                errors.append({'row': i, 'name': name, 'error': 'duration_value must be a whole number'})
                continue

            is_active_raw = (row.get('is_active') or 'true').strip().lower()
            is_active = is_active_raw not in {'false', '0', 'no'}

            plan = BillingPlan.objects.create(
                name=name,
                description=(row.get('description') or '').strip(),
                service_type=service_type,
                download_speed=download_speed,
                upload_speed=upload_speed,
                price=price,
                duration_value=duration_value,
                duration_unit=duration_unit,
                duration_days=duration_value if duration_unit == 'days' else 30,
                data_limit_gb=data_limit_gb,
                mikrotik_profile=mikrotik_profile,
                is_active=is_active,
            )
            created.append({'row': i, 'name': plan.name, 'id': plan.id})

        return Response({
            'success': True,
            'created_count': len(created),
            'error_count': len(errors),
            'created': created,
            'errors': errors,
        })


class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View customer subscriptions
    """
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Subscription.objects.filter(customer=self.request.user)
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """
        Get current active subscription
        """
        subscription = Subscription.objects.filter(
            customer=request.user,
            status='active'
        ).first()
        
        if subscription:
            serializer = self.get_serializer(subscription)
            return Response(serializer.data)
        
        return Response({
            'message': 'No active subscription'
        }, status=status.HTTP_404_NOT_FOUND)


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View payment transactions
    """
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Transaction.objects.filter(customer=self.request.user)


class UsageRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View usage records
    """
    serializer_class = UsageRecordSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return UsageRecord.objects.filter(customer=self.request.user)


from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from django.utils import timezone
from django.db import transaction
import random
import string
from apps.billing.models import Voucher, VoucherBatch
from apps.billing.serializers import (
    VoucherBatchSerializer, VoucherGenerationSerializer, VoucherRedeemSerializer
)


class VoucherBatchViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List voucher batches
    """
    queryset = VoucherBatch.objects.all()
    serializer_class = VoucherBatchSerializer
    permission_classes = [RoleAllowed('admin', 'sales')]


class VoucherGenerationView(APIView):
    """
    Generate bulk vouchers (admin/sales only)
    """
    permission_classes = [RoleAllowed('admin', 'sales')]
    
    def post(self, request):
        serializer = VoucherGenerationSerializer(data=request.data)
        if serializer.is_valid():
            quantity = serializer.validated_data['quantity']
            value = serializer.validated_data.get('value')
            plan_id = serializer.validated_data.get('plan_id')
            note = serializer.validated_data.get('note', '')
            
            plan = None
            if plan_id:
                try:
                    plan = BillingPlan.objects.get(id=plan_id)
                    value = plan.price # Use plan price as value if not explicit
                except BillingPlan.DoesNotExist:
                     return Response({'error': 'Invalid plan ID'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Create Batch
            with transaction.atomic():
                batch = VoucherBatch.objects.create(
                    quantity=quantity,
                    value=value or 0,
                    plan=plan,
                    generated_by=request.user,
                    note=note
                )
                
                vouchers_to_create = []
                # Use uppercase and digits for 6-char codes to ensure enough entropy
                chars = string.ascii_uppercase + string.digits
                
                for _ in range(quantity):
                    # Generate 6-char alphanumeric code
                    code = ''.join(random.choices(chars, k=6))
                    # Ensure uniqueness
                    while Voucher.objects.filter(code=code).exists():
                        code = ''.join(random.choices(chars, k=6))
                        
                    vouchers_to_create.append(Voucher(
                        batch=batch,
                        code=code,
                        amount=value or 0,
                        plan=plan,
                        status='active'
                    ))
                
                Voucher.objects.bulk_create(vouchers_to_create)
            
            # Refetch batch to include vouchers in serialization
            batch = VoucherBatch.objects.prefetch_related('vouchers').get(id=batch.id)
            
            return Response(
                VoucherBatchSerializer(batch).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VoucherRedeemView(APIView):
    """
    Redeem a voucher code
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = VoucherRedeemSerializer(data=request.data)
        if serializer.is_valid():
            code = serializer.validated_data['code']
            mac_address = serializer.validated_data.get('mac_address') or None
            
            try:
                voucher = Voucher.objects.select_related('plan').get(code=code)
            except Voucher.DoesNotExist:
                return Response({'error': 'Invalid voucher code'}, status=status.HTTP_400_BAD_REQUEST)
            
            if voucher.status != 'active':
                return Response({'error': 'Voucher has already been used'}, status=status.HTTP_400_BAD_REQUEST)
            
            if voucher.expiry_date and voucher.expiry_date < timezone.now():
                return Response({'error': 'Voucher has expired'}, status=status.HTTP_400_BAD_REQUEST)

            # Check if voucher has a plan associated (REQUIRED for auto-account creation)
            if not voucher.plan:
                 return Response({'error': 'This voucher is not linked to a plan. Cannot auto-redeem.'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Redeem logic
            with transaction.atomic():
                # Lock voucher row
                voucher = Voucher.objects.select_for_update().get(id=voucher.id)
                
                if voucher.status != 'active':
                     return Response({'error': 'Voucher already used'}, status=status.HTTP_400_BAD_REQUEST)
                
                # 1. Create Customer
                # Check if user already exists
                from apps.customers.models import Customer
                
                username = voucher.code
                if Customer.objects.filter(username=username).exists():
                     # User exists, append random 3 digits to ensure unique new user record
                     import random
                     suffix = ''.join(random.choices('0123456789', k=3))
                     username = f"{voucher.code}{suffix}"
                
                customer = Customer.objects.create(
                    username=username,
                    # Inherit service type from the plan
                    service_type=voucher.plan.service_type,
                    status='active',
                    phone_number='',
                    first_name='',
                    last_name='',
                )
                
                customer.set_password(voucher.code) # Password = Voucher Code
                
                # Set credentials based on plan service type
                if voucher.plan.service_type in ['pppoe', 'both']:
                    customer.pppoe_username = customer.username
                    customer.pppoe_password = voucher.code
                
                if voucher.plan.service_type in ['hotspot', 'both']:
                    customer.hotspot_username = customer.username
                    customer.hotspot_password = voucher.code
                    if mac_address:
                        customer.hotspot_mac_address = mac_address

                customer.save()
                
                # Logic used to vary if using get_or_create, now significantly simplified for "always create new" logic requested
                created = True
                
                # 2. Update Voucher
                voucher.status = 'used'
                voucher.used_by = customer
                voucher.used_at = timezone.now()
                voucher.save()
                
                # 3. Create Subscription
                from apps.billing.models import Subscription
                
                # Calculate expiry
                expiry_date = timezone.now() + voucher.plan.get_duration_timedelta()
                
                Subscription.objects.create(
                    customer=customer,
                    plan=voucher.plan,
                    expiry_date=expiry_date,
                    status='active'
                )
                
                # 4. Generate Tokens
                from rest_framework_simplejwt.tokens import RefreshToken
                from apps.customers.serializers import CustomerSerializer
                
                refresh = RefreshToken.for_user(customer)

            return Response({
                'success': True,
                'message': f'Voucher redeemed! Subscribed to {voucher.plan.name}.',
                'customer': CustomerSerializer(customer).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            })
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ManualSubscriptionView(APIView):
    """
    Manually create a customer (PPPoE or Hotspot) -- or renew/assign a plan
    to an existing one, by username -- and activate their subscription.
    When a new customer is created, portal login and PPPoE/Hotspot
    credentials (same username/password, matching the self-service
    registration flow) are issued and returned once so the admin can hand
    them to the customer. (Admin/Sales only)
    """
    permission_classes = [RoleAllowed('admin', 'sales')]

    def post(self, request):
        from apps.customers.models import Customer

        data = request.data
        username = (data.get('username') or '').strip()
        plan_id = data.get('plan_id')
        password = data.get('password') or ''
        service_type = data.get('service_type') or 'pppoe'

        if not username:
            return Response({'error': 'username is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = BillingPlan.objects.get(id=plan_id)
        except (BillingPlan.DoesNotExist, TypeError, ValueError):
            return Response({'error': 'Invalid plan ID'}, status=status.HTTP_400_BAD_REQUEST)

        created_new = False
        customer = Customer.objects.filter(username=username).first()

        if not customer:
            phone_number = (data.get('phone_number') or '').strip()
            if not phone_number:
                return Response({'error': 'phone_number is required to create a new customer'}, status=status.HTTP_400_BAD_REQUEST)

            if not password:
                password = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

            customer = Customer.objects.create(
                username=username,
                email=data.get('email', ''),
                phone_number=phone_number,
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                service_type=service_type,
                status='pending',
                is_verified=True,
            )
            customer.set_password(password)
            if service_type in ['pppoe', 'both']:
                customer.pppoe_username = username
                customer.pppoe_password = password
            if service_type in ['hotspot', 'both']:
                customer.hotspot_username = username
                customer.hotspot_password = password
            if service_type == 'static':
                static_ip = (data.get('static_ip_address') or '').strip()
                if not static_ip:
                    customer.delete()
                    return Response({'error': 'static_ip_address is required for Static IP customers'}, status=status.HTTP_400_BAD_REQUEST)
                customer.static_ip_address = static_ip
            customer.save()
            created_new = True
        elif plan.service_type == 'static' and not customer.static_ip_address:
            static_ip = (data.get('static_ip_address') or '').strip()
            if not static_ip:
                return Response(
                    {'error': 'static_ip_address is required to assign a Static IP plan to this customer'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            customer.static_ip_address = static_ip
            customer.service_type = 'static'
            customer.save(update_fields=['static_ip_address', 'service_type'])

        from apps.billing.services import apply_subscription
        subscription, credited = apply_subscription(customer, plan)

        Transaction.objects.create(
            customer=customer,
            subscription=subscription,
            transaction_id='MANUAL-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10)),
            amount=plan.price,
            payment_method='cash',
            status='completed',
            notes=f"Manual activation by {request.user.username}"
        )

        message = f'Subscription activated for {customer.username}'
        if credited:
            message += f' (KES {credited} credited to their balance from the previous plan)'

        response_data = {
            'success': True,
            'message': message,
            'subscription_id': subscription.id,
        }
        if created_new:
            response_data['credentials'] = {
                'portal_username': customer.username,
                'portal_password': password,
                'pppoe_username': customer.pppoe_username,
                'pppoe_password': customer.pppoe_password,
                'hotspot_username': customer.hotspot_username,
                'hotspot_password': customer.hotspot_password,
                'static_ip_address': customer.static_ip_address,
            }
        return Response(response_data)


class PurchaseWithBalanceView(APIView):
    """
    Self-service counterpart to SubscriberViewSet.switch_plan (admin-only):
    a logged-in customer buys/renews/upgrades/downgrades their own
    subscription paid entirely out of their own account_balance, with no
    M-Pesa STK push involved -- see apps.billing.services.purchase_plan_from_balance.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import random
        import string
        from apps.billing.services import purchase_plan_from_balance, InsufficientBalance

        customer = request.user
        try:
            plan = BillingPlan.objects.get(id=request.data.get('plan_id'), is_active=True)
        except (BillingPlan.DoesNotExist, TypeError, ValueError):
            return Response({'error': 'Invalid plan ID'}, status=status.HTTP_400_BAD_REQUEST)

        if plan.service_type == 'static':
            return Response(
                {'error': 'This plan requires setup by our team. Please contact support.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            subscription, credited = purchase_plan_from_balance(customer, plan)
        except InsufficientBalance as e:
            return Response({
                'error': f"Insufficient balance: KES {e.available} available, KES {e.required} required for {plan.name}."
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': f'Could not activate this plan: {e}'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        Transaction.objects.create(
            customer=customer,
            subscription=subscription,
            transaction_id='SELFBAL-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10)),
            amount=plan.price,
            payment_method='balance',
            status='completed',
            notes=(
                f"Self-service purchase from balance"
                + (f" (KES {credited} credited from previous plan)" if credited else "")
            ),
        )

        return Response({
            'success': True,
            'message': f'You are now on {plan.name}',
            'account_balance': customer.account_balance,
        })


class PPPoEImportTemplateView(APIView):
    """Downloadable CSV template for bulk-importing PPPoE customers."""
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request):
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="pppoe_users_template.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'username', 'password', 'first_name', 'last_name', 'phone_number',
            'email', 'plan_name', 'expiry_date',
        ])
        writer.writerow([
            'jdoe', 'SecurePass123', 'John', 'Doe', '0712345678',
            'jdoe@example.com', 'Home 10Mbps', '',
        ])
        return response


class PPPoEBulkImportView(APIView):
    """
    Bulk-create PPPoE customers from an uploaded CSV (see
    PPPoEImportTemplateView for the expected columns). Each row's username/
    password become BOTH the portal login and the PPPoE login, matching
    ManualSubscriptionView's convention for a single manually-created
    customer -- and each row immediately activates on the router the same
    way (via Subscription's post_save signal), so an imported user is fully
    ready to connect, not just a DB row.

    Existing usernames are rejected per-row rather than modified -- this is
    for onboarding customers who don't exist in the system yet, not for
    bulk-editing existing ones.

    expiry_date (YYYY-MM-DD) is optional: provide it to preserve a
    customer's real remaining time when migrating them in from elsewhere;
    leave it blank for a fresh full-duration subscription starting today.
    No Transaction is created for imported rows -- these aren't real
    payments taken through this system, and fabricating one would distort
    revenue reports.
    """
    permission_classes = [RoleAllowed('admin', 'sales')]

    def post(self, request):
        import csv
        import io
        from datetime import datetime
        from apps.customers.models import Customer

        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({'error': 'file is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            decoded = csv_file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response({'error': 'File must be UTF-8 encoded CSV'}, status=status.HTTP_400_BAD_REQUEST)

        reader = csv.DictReader(io.StringIO(decoded))
        required_cols = {'username', 'password', 'phone_number', 'plan_name'}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            missing = required_cols - set(reader.fieldnames or [])
            return Response(
                {'error': f'CSV is missing required column(s): {", ".join(sorted(missing))}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        created, errors = [], []

        for i, row in enumerate(reader, start=2):  # row 1 is the header
            username = (row.get('username') or '').strip()
            password = (row.get('password') or '').strip()
            phone_number = (row.get('phone_number') or '').strip()
            plan_name = (row.get('plan_name') or '').strip()

            if not username or not password or not phone_number or not plan_name:
                errors.append({'row': i, 'username': username, 'error': 'username, password, phone_number and plan_name are required'})
                continue

            if len(password) < 8:
                errors.append({'row': i, 'username': username, 'error': 'password must be at least 8 characters'})
                continue

            if Customer.objects.filter(username=username).exists():
                errors.append({'row': i, 'username': username, 'error': 'Username already exists'})
                continue

            plan = BillingPlan.objects.filter(name__iexact=plan_name).first()
            if not plan:
                errors.append({'row': i, 'username': username, 'error': f'No billing plan named "{plan_name}"'})
                continue

            expiry_raw = (row.get('expiry_date') or '').strip()
            if expiry_raw:
                try:
                    expiry_date = timezone.make_aware(datetime.strptime(expiry_raw, '%Y-%m-%d'))
                except ValueError:
                    errors.append({'row': i, 'username': username, 'error': 'expiry_date must be YYYY-MM-DD'})
                    continue
            else:
                expiry_date = timezone.now() + plan.get_duration_timedelta()

            try:
                with transaction.atomic():
                    customer = Customer.objects.create(
                        username=username,
                        email=(row.get('email') or '').strip(),
                        phone_number=phone_number,
                        first_name=(row.get('first_name') or '').strip(),
                        last_name=(row.get('last_name') or '').strip(),
                        service_type='pppoe',
                        status='pending',
                        is_verified=True,
                        pppoe_username=username,
                        pppoe_password=password,
                    )
                    customer.set_password(password)
                    customer.save()

                    Subscription.objects.create(
                        customer=customer,
                        plan=plan,
                        expiry_date=expiry_date,
                        status='active',
                    )
                created.append({'row': i, 'username': username})
            except Exception as e:
                errors.append({'row': i, 'username': username, 'error': str(e)})

        return Response({
            'success': True,
            'created_count': len(created),
            'error_count': len(errors),
            'created': created,
            'errors': errors,
        })
