import json
import logging

from apps.audit import context
from apps.audit.utils import mask

logger = logging.getLogger('audit')

SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}
# Logged their own way (sign-ins) or pure noise (token refresh every few
# minutes per open tab).
SKIP_REQUEST_PATHS = ('/api/customers/login/', '/api/customers/token/refresh/', '/api/token/refresh/')


class AuditMiddleware:
    """
    Sets the audit context for the request, and after the response writes
    one 'request' row for every change-making request by a signed-in user
    (method, path, status, the body with secrets masked). That row is the
    record of actions that change nothing in the database (reboot a
    router, send messages, test a gateway); model changes made by the same
    request get their own rows with the same request_id.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        source = 'admin' if request.path.startswith('/django-admin/') else 'web'
        token = context.start(request=request, source=source)
        # Read before the view consumes the stream.
        body = None
        if request.method not in SAFE_METHODS and not request.path.startswith(SKIP_REQUEST_PATHS):
            try:
                body = self._body(request)
            except Exception:
                body = None
        try:
            response = self.get_response(request)
            if body is not None:
                self._log_request(request, response, body)
            return response
        finally:
            context.end(token)

    @staticmethod
    def _body(request):
        ctype = request.content_type or ''
        if 'json' in ctype:
            raw = request.body
            if len(raw) > 20000:
                return {'_note': f'body not kept ({len(raw)} bytes)'}
            try:
                return mask(json.loads(raw or b'{}'))
            except ValueError:
                return {'_note': 'body was not valid JSON'}
        if 'multipart' in ctype:
            return {'files': list(request.FILES.keys()), **mask({k: v for k, v in request.POST.items()})}
        if 'form' in ctype:
            return mask({k: v for k, v in request.POST.items()})
        return {}

    @staticmethod
    def _log_request(request, response, body):
        user = getattr(request, 'user', None)
        if not (user is not None and user.is_authenticated):
            return
        try:
            from apps.audit.signals import create_row
            fields = context.actor_fields()
            text = json.dumps(body, default=str)
            if len(text) > 4000:
                body = {'_truncated': text[:4000]}
            create_row(
                action='request', status_code=response.status_code,
                object_repr=f'{request.method} {request.path}'[:255],
                changes={'body': body} if body else {}, **fields,
            )
        except Exception:
            logger.exception('Could not write the audit request row')
