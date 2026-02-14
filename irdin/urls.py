"""
URL configuration for irdin project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import mimetypes
import os
import re

from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.urls import path, re_path

from palestras.views import palestra_detail, search

FRONTEND_INDEX = settings.BASE_DIR / "static" / "frontend" / "index.html"


def serve_frontend(request):
    return FileResponse(open(FRONTEND_INDEX, "rb"), content_type="text/html")


def serve_media(request, path):
    """Serve media files with Range request support for audio/video seeking."""
    fullpath = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.isfile(fullpath):
        raise Http404
    content_type, _ = mimetypes.guess_type(fullpath)
    content_type = content_type or "application/octet-stream"
    file_size = os.path.getsize(fullpath)
    range_header = request.META.get("HTTP_RANGE")
    if range_header:
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1
            f = open(fullpath, "rb")
            f.seek(start)
            response = HttpResponse(f.read(length), content_type=content_type, status=206)
            response["Content-Length"] = length
            response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            response["Accept-Ranges"] = "bytes"
            return response
    response = FileResponse(open(fullpath, "rb"), content_type=content_type)
    response["Accept-Ranges"] = "bytes"
    response["Content-Length"] = file_size
    return response


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/search', search),
    path('api/palestras/<slug:slug>', palestra_detail),
]

if settings.DEBUG:
    urlpatterns += [path('media/<path:path>', serve_media)]

# Catch-all: serve the React app for any non-API/admin/static path
urlpatterns += [
    re_path(r"^(?!api/|admin/|static/|media/).*$", serve_frontend),
]
