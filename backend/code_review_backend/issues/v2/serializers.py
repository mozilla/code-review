from rest_framework import serializers

from code_review_backend.issues.models import IssueLink


class IssueLinkHashSerializer(serializers.ModelSerializer):
    """Serialize an Issue hash from the IssueLink M2M"""

    id = serializers.UUIDField(source="issue_id", read_only=True)
    hash = serializers.CharField(source="issue__hash", max_length=32, read_only=True)

    class Meta:
        model = IssueLink
        fields = ("id", "hash")


class DiffIssuesSerializer(serializers.Serializer):
    previous_diff_id = serializers.UUIDField(allow_null=True, read_only=True)
    issues = IssueLinkHashSerializer(many=True)
