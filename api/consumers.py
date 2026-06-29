"""WebSocket consumers for real-time device ↔ server communication.

Security: device auth uses hashed passwords with automatic legacy upgrade.
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import Device, ShiftAssignment, GuardSupervisor, OperatorAlert
from api.password import verify_device_password, hash_device_password


class GuardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.device_id = None
        self.group_name = None
        await self.accept()

    async def disconnect(self, close_code):
        if self.device_id:
            await self._set_device_online(False)
            if self.group_name:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            await self._broadcast_connection_status(False)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(json.dumps({'error': 'Invalid JSON'}))
            return

        event_type = data.get('type')

        if event_type == 'AUTH':
            await self._handle_auth(data)
        elif event_type == 'LOCATION_UPDATE':
            await self._handle_location(data)
        elif event_type == 'SCAN_EVENT':
            await self._handle_scan(data)
        elif event_type == 'TTS_ACK':
            await self._handle_tts_ack(data)
        else:
            await self.send(json.dumps({'error': f'Unknown event type: {event_type}'}))

    async def _handle_auth(self, data):
        device_id = data.get('device_id')
        password = data.get('password')
        if not device_id or not password:
            await self.send(json.dumps({'error': 'device_id and password required'}))
            return

        device = await self._authenticate_device(device_id, password)
        if not device:
            await self.send(json.dumps({'error': 'Authentication failed'}))
            return

        self.device_id = device_id
        self.group_name = f'guard_{device_id}'
        self.org_group = f'org_{device.organization_id}' if device.organization_id else None

        await self._set_device_online(True)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        if self.org_group:
            await self.channel_layer.group_add(self.org_group, self.channel_name)

        await self._broadcast_connection_status(True)
        await self.send(json.dumps({'type': 'AUTH_OK', 'device_id': device_id}))

    async def _handle_location(self, data):
        if not self.device_id:
            await self.send(json.dumps({'error': 'Not authenticated'}))
            return

        lat = data.get('lat')
        lng = data.get('lng')
        accuracy = data.get('accuracy')
        battery = data.get('battery_pct')

        await self._update_device_location(lat, lng, accuracy, battery)

        broadcast = {
            'type': 'location_update',
            'device_id': self.device_id,
            'lat': lat,
            'lng': lng,
            'accuracy': accuracy,
            'battery_pct': battery,
            'timestamp': timezone.now().isoformat(),
        }

        if self.org_group:
            await self.channel_layer.group_send(self.org_group, broadcast)
        else:
            await self.channel_layer.group_send(self.group_name, broadcast)

    async def _handle_scan(self, data):
        if not self.device_id:
            await self.send(json.dumps({'error': 'Not authenticated'}))
            return

        nfc_value = data.get('nfc_value')
        lat = data.get('lat')
        lng = data.get('lng')

        broadcast = {
            'type': 'scan_event',
            'device_id': self.device_id,
            'nfc_value': nfc_value,
            'lat': lat,
            'lng': lng,
            'timestamp': timezone.now().isoformat(),
        }

        if self.org_group:
            await self.channel_layer.group_send(self.org_group, broadcast)

        await self.send(json.dumps({'type': 'SCAN_RECEIVED', 'nfc_value': nfc_value}))

    async def _handle_tts_ack(self, data):
        if not self.device_id:
            return
        await self._clear_tts_pending()

    async def _broadcast_connection_status(self, is_online):
        broadcast = {
            'type': 'connection_status',
            'device_id': self.device_id,
            'is_online': is_online,
            'timestamp': timezone.now().isoformat(),
        }
        if self.org_group:
            await self.channel_layer.group_send(self.org_group, broadcast)

    async def location_update(self, event):
        await self.send(json.dumps(event))

    async def scan_event(self, event):
        await self.send(json.dumps(event))

    async def connection_status(self, event):
        await self.send(json.dumps(event))

    async def tts_command(self, event):
        await self.send(json.dumps({
            'type': 'TTS_COMMAND',
            'message': event.get('message'),
            'tts_voice': event.get('tts_voice', 'en-US'),
            'tts_rate': event.get('tts_rate', 1.0),
            'tts_pitch': event.get('tts_pitch', 1.0),
        }))

    @database_sync_to_async
    def _authenticate_device(self, device_id, password):
        device = Device.objects.filter(device_id=device_id).first()
        if not device:
            return None
        is_valid, needs_rehash = verify_device_password(password, device.password)
        if not is_valid:
            return None
        if needs_rehash:
            Device.objects.filter(id=device.id).update(password=hash_device_password(password))
        return device

    @database_sync_to_async
    def _set_device_online(self, online):
        if not self.device_id:
            return
        Device.objects.filter(device_id=self.device_id).update(
            is_online=online,
            last_seen=timezone.now() if online else None,
        )

    @database_sync_to_async
    def _update_device_location(self, lat, lng, accuracy, battery):
        if not self.device_id:
            return
        updates = {
            'last_latitude': lat,
            'last_longitude': lng,
            'last_gps_accuracy': accuracy,
            'battery_pct': battery,
            'last_seen': timezone.now(),
            'is_online': True,
        }
        Device.objects.filter(device_id=self.device_id).update(**updates)

    @database_sync_to_async
    def _clear_tts_pending(self):
        if not self.device_id:
            return
        Device.objects.filter(device_id=self.device_id).update(
            tts_pending=None,
            tts_pending_voice='',
            tts_pending_rate=1.0,
            tts_pending_pitch=1.0,
            tts_pending_at=None,
            tts_acked=True,
        )


class DispatcherConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for dispatcher dashboards to receive real-time updates."""

    async def connect(self):
        self.user = self.scope.get('user')
        self.org_group = None
        if self.user and self.user.is_authenticated:
            org = await self._get_dispatcher_org()
            if org:
                self.org_group = f'org_{org}'
                await self.channel_layer.group_add(self.org_group, self.channel_name)
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if self.org_group:
            await self.channel_layer.group_discard(self.org_group, self.channel_name)

    async def receive(self, text_data):
        pass

    async def location_update(self, event):
        await self.send(json.dumps(event))

    async def scan_event(self, event):
        await self.send(json.dumps(event))

    async def connection_status(self, event):
        await self.send(json.dumps(event))

    @database_sync_to_async
    def _get_dispatcher_org(self):
        user = self.scope.get('user')
        if hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
            return user.dispatcher_profile.organization.id
        return None
