from django import forms
from django.forms import inlineformset_factory
from api.models import PatrolRoute, Checkpoint

class PatrolRouteForm(forms.ModelForm):
    class Meta:
        model = PatrolRoute
        fields = [
            'name', 'description', 'enforce_order', 'enforce_time', 
            'is_geofence', 'is_emergency', 'is_audit', 'is_daily', 
            'scheduled_start_time', 'send_start_alert', 
            'start_alert_lead_time', 'readout_text', 'assigned_guards'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Detailed route description...'}),
            'readout_text': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Audio instructions for radio...'}),
        }

CheckpointFormSet = inlineformset_factory(
    PatrolRoute, 
    Checkpoint,
    fields=['name', 'nfc_tag', 'lat', 'lng', 'order', 'planned_time', 'time_tolerance'],
    extra=1,
    can_delete=True
)