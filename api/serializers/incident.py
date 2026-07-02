from rest_framework import serializers

from api.models.scanning import IncidentReport


class IncidentReportSerializer(serializers.ModelSerializer):
    guard_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    def get_guard_name(self, obj: IncidentReport) -> str:
        if obj.guard_supervisor:
            return f"{obj.guard_supervisor.first_name} {obj.guard_supervisor.last_name}".strip()
        return "System"

    class Meta:
        model = IncidentReport
        fields = '__all__'
