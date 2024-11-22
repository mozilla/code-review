# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.conf import settings
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from code_review_backend.issues import api, api_v2

# Build Swagger schema view
schema_view = get_schema_view(
    openapi.Info(
        title="Mozilla Code Review API",
        default_version="v1",
        description="Mozilla Code Review Backend API",
        contact=openapi.Contact(email="release-mgmt-analysis@mozilla.com"),
        license=openapi.License(name="MPL2"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path("", lambda request: redirect("docs/", permanent=False)),
    path("v1/", include(api.urls)),
    path("v2/", include(api_v2.urls)),
    path("admin/", admin.site.urls),
    path(
        r"docs<format>\.json|\.yaml)",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    path(
        r"docs/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
