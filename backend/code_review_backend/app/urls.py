# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path

urlpatterns = [
    path("", lambda request: redirect("admin/", permanent=False)),
    path("admin/", admin.site.urls),
]
