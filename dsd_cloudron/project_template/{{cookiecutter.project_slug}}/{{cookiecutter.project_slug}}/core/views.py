from django.http import HttpResponse


def healthz(request):
    """200 response for the Cloudron health check."""
    return HttpResponse("ok", content_type="text/plain")
