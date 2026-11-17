from rest_framework.permissions import BasePermission


class IsPlatform(BasePermission):
    """Platform team (admins and support)."""
    message = 'Platform staff only.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_platform)


class IsPlatformAdmin(BasePermission):
    """Platform admins: settings, money movements, the team."""
    message = 'Platform admins only.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_platform_admin)


class IsPlatformOrReadOnlyStaff(BasePermission):
    """Support staff can look; only admins can change."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and u.is_platform):
            return False
        return request.method in ('GET', 'HEAD', 'OPTIONS') or u.is_platform_admin


class IsTenantOwner(BasePermission):
    message = 'This is the ISP account area.'

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.tenant_id and u.role == 'isp_owner')
