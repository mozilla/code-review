# Generated by Django 5.1.1 on 2024-10-14 13:36

import tqdm
from django.db import migrations, models
from django.db.models import Count


def deduplicate_issues_v1(apps, schema_editor):
    Issue = apps.get_model("issues", "Issue")
    IssueLink = apps.get_model("issues", "IssueLink")

    nb_before = Issue.objects.count()

    # Group issues by hash, finding duplicates
    issues = (
        Issue.objects.values_list("hash")
        .annotate(nb=Count("hash"))
        .filter(nb__gt=1)
        .order_by("-nb")
    )

    for hash, nb in tqdm.tqdm(issues.iterator(), total=issues.count()):
        # There is a unique constraint on IssueLink issue + revision + diff
        # so we need to keep only one link per group
        links = (
            IssueLink.objects.filter(issue__hash=hash)
            .values_list("revision_id", "diff_id")
            .annotate(nb=Count("*"))
            .filter(nb__gt=1)
        )
        for revision_id, diff_id, nb in links:
            qs = IssueLink.objects.filter(
                issue__hash=hash, revision_id=revision_id, diff_id=diff_id
            )
            link = qs.first()
            qs.exclude(id=link.id).delete()

        # Then we can update all remaining issue links for that hash
        issue = Issue.objects.filter(hash=hash).first()
        IssueLink.objects.filter(issue__hash=hash).exclude(issue_id=issue.id).update(
            issue_id=issue.id
        )

        # And finally delete duplicate issues
        Issue.objects.filter(hash=hash).exclude(id=issue.id).delete()

    nb_after = Issue.objects.count()

    print(f"Issues total went from {nb_before} to {nb_after}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("issues", "0012_move_issues_attributes"),
    ]

    operations = [
        migrations.RunPython(deduplicate_issues_v1),
        migrations.AlterField(
            model_name="issue",
            name="hash",
            field=models.CharField(max_length=250, unique=True),
        ),
    ]
