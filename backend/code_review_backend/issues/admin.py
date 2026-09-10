# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib import admin

from code_review_backend.issues.models import Diff, Issue, Repository, Revision


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ("slug", "url")


class DiffInline(admin.TabularInline):
    # Read only inline
    model = Diff
    readonly_fields = (
        "id",
        "repository",
        "mercurial_hash",
        "provider_id",
        "review_task_id",
    )


@admin.register(Revision)
class RevisionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "provider_id",
        "title",
        "bugzilla_id",
        "base_repository",
        "head_repository",
    )
    list_filter = (
        "base_repository",
        "head_repository",
        "provider",
    )
    inlines = (DiffInline,)


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_filter = ("analyzer",)
    list_display = (
        "id",
        "path",
        "level",
        "analyzer",
        "analyzer_check",
        "created",
    )
    search_fields = ("line", "analyzer", "path")
    ordering = ("-created",)


# Naming
admin.site.site_header = "Mozilla Code Review Backend"
