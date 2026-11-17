from django.contrib.auth import authenticate, get_user_model, password_validation
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from cloud.accounts.permissions import IsPlatformAdmin

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    is_platform = serializers.BooleanField(read_only=True)
    is_platform_admin = serializers.BooleanField(read_only=True)
    tenant_slug = serializers.CharField(source='tenant.slug', default=None, read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name', 'phone', 'role', 'is_active',
                  'is_superuser', 'is_platform', 'is_platform_admin', 'tenant', 'tenant_slug', 'last_login', 'date_joined']
        read_only_fields = ['is_superuser', 'tenant', 'last_login', 'date_joined']

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.email


def tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {'access': str(refresh.access_token), 'refresh': str(refresh)}


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
def login(request):
    email = (request.data.get('email') or request.data.get('username') or '').strip().lower()
    password = request.data.get('password') or ''
    user = User.objects.filter(email__iexact=email).first()
    user = authenticate(request, username=user.username, password=password) if user else None
    if not user or not user.is_active:
        return Response({'error': 'Wrong email or password'}, status=status.HTTP_401_UNAUTHORIZED)
    from django.contrib.auth.models import update_last_login
    update_last_login(None, user)
    return Response({'user': UserSerializer(user).data, **tokens_for(user)})


login.cls.throttle_scope = 'login'


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        s = UserSerializer(request.user, data={k: v for k, v in request.data.items()
                                               if k in ('first_name', 'last_name', 'phone')}, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


class ChangePasswordView(APIView):
    def post(self, request):
        user = request.user
        if not user.check_password(request.data.get('current_password') or ''):
            return Response({'error': 'Your current password is wrong'}, status=400)
        new = request.data.get('new_password') or ''
        try:
            password_validation.validate_password(new, user)
        except Exception as e:
            return Response({'error': ' '.join(getattr(e, 'messages', [str(e)]))}, status=400)
        user.set_password(new)
        user.save()
        return Response({'ok': True})


class TeamSerializer(UserSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['password']

    def validate_role(self, v):
        if v not in ('platform_admin', 'platform_staff'):
            raise serializers.ValidationError('Team members are platform admins or support staff.')
        return v

    def create(self, data):
        password = data.pop('password', None)
        if not password:
            raise serializers.ValidationError({'password': 'Set a password for the new team member.'})
        password_validation.validate_password(password)
        user = User(username=data['email'].lower(), **data)
        user.email = user.email.lower()
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, data):
        password = data.pop('password', None)
        user = super().update(instance, data)
        if password:
            password_validation.validate_password(password, user)
            user.set_password(password)
            user.save()
        return user


class TeamView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        qs = User.objects.filter(role__in=['platform_admin', 'platform_staff']) | User.objects.filter(is_superuser=True)
        return Response(TeamSerializer(qs.distinct().order_by('email'), many=True).data)

    def post(self, request):
        s = TeamSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data, status=201)


class TeamMemberView(APIView):
    permission_classes = [IsPlatformAdmin]

    def patch(self, request, pk):
        user = User.objects.filter(pk=pk).exclude(role='isp_owner').first()
        if not user:
            return Response(status=404)
        if user == request.user and request.data.get('is_active') is False:
            return Response({'error': "You can't deactivate yourself"}, status=400)
        s = TeamSerializer(user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)
