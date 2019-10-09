# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib import admin

from code_review_backend.issues.models import Diff
from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import Repository
from code_review_backend.issues.models import Revision


class RepositoryAdmin(admin.ModelAdmin):
    list_display = ("slug", "url")


class DiffInline(admin.TabularInline):
    # Read only inline
    model = Diff
    readonly_fields = ("id", "phid", "review_task_id")


class RevisionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "bugzilla_id", "repository")
    list_filter = ("repository",)
    inlines = (DiffInline,)


class IssueAdmin(admin.ModelAdmin):
    list_display = ("id", "path", "line", "level", "analyzer", "check", "diff")


admin.site.register(Repository, RepositoryAdmin)
admin.site.register(Revision, RevisionAdmin)
admin.site.register(Issue, IssueAdmin)
