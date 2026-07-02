from rest_framework import serializers

from api.models.scanning import OperatorAlert


class OperatorAlertSerializer(serializers.ModelSerializer):
    operator_name = serializers.SerializerMethodField()

    def get_operator_name(self, obj: OperatorAlert) -> str | None:
        return obj.operator.first_name if obj.operator else None

    class Meta:
        model = OperatorAlert
        fields = '__all__'
