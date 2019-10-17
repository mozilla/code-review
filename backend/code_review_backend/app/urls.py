# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include
from django.urls import path

from code_review_backend.issues import api

urlpatterns = [
    path("", lambda request: redirect("v1/", permanent=False)),
    path("v1/", include(api.router.urls)),
    path("admin/", admin.site.urls),
]
