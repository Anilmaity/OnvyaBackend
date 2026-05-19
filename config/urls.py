from django.contrib import admin
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.conf.urls.static import static

from config.graphql import AuthenticatedGraphQLView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("graphql/", csrf_exempt(AuthenticatedGraphQLView.as_view(graphiql=settings.DEBUG))),
    path("", include("apps.payments.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
