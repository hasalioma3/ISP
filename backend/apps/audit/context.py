"""
Who/where the current change comes from. The middleware puts the request
here, Celery's task_prerun the task name; signals read it when they write a
log row. A ContextVar (not a thread-local) so gthread workers and anything
async each see their own.

The request object itself is stored, not the user: SimpleJWT authenticates
inside the DRF view, after middleware has run, and DRF writes the user back
onto the underlying Django request -- so reading request.user at log time
gets the real staff account instead of AnonymousUser.
"""
import contextvars
import uuid

_ctx = contextvars.ContextVar('audit_ctx', default=None)


def start(**values):
    values.setdefault('request_id', uuid.uuid4().hex)
    return _ctx.set(values)


def end(token):
    _ctx.reset(token)


def current():
    return _ctx.get() or {}


def client_ip(request):
    # nginx sets X-Forwarded-For / X-Real-IP; REMOTE_ADDR is then the proxy.
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    ip = forwarded.split(',')[0].strip() if forwarded else request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')
    return ip or None


def actor_fields():
    """actor/actor_username/actor_role/source/ip/... for a new AuditLog row."""
    ctx = current()
    request = ctx.get('request')
    fields = {
        'source': ctx.get('source', 'system'),
        'request_id': ctx.get('request_id', ''),
        'actor_username': ctx.get('actor_username', ''),
    }
    if request is not None:
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            fields['actor'] = user
            fields['actor_username'] = user.get_username()
            fields['actor_role'] = 'superadmin' if user.is_superuser else (getattr(user, 'role', '') if user.is_staff else 'subscriber')
        fields.update(
            ip_address=client_ip(request),
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
            method=request.method,
            path=request.path[:255],
        )
    return fields
