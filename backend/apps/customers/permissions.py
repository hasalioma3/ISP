from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    """
    Base class for role-gated admin endpoints. Requires an authenticated
    staff user whose `role` is in `allowed_roles`. Superusers always pass,
    regardless of role, so the original admin account never gets locked out.
    """
    allowed_roles = ()

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_staff):
            return False
        if user.is_superuser:
            return True
        return user.role in self.allowed_roles


def RoleAllowed(*roles):
    """
    permission_classes = [RoleAllowed('admin', 'technician')]
    """
    return type('RoleAllowed', (HasRole,), {'allowed_roles': roles})
