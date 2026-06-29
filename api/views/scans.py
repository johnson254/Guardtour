from django.utils import timezone
from django.db.models import Q
from datetime import datetime
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.throttling import AnonRateThrottle
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, status, filters

from api.models import (
    Device,
    DeviceTrail,
    GuardSupervisor,
    Organization,
    PatrolRoute,
    ScanRecord,
    ShiftAssignment,
    Checkpoint,
)
from api.serializers import ScanRecordSerializer
from api.services.scan import process_scan
from api.services.gps import correct_gps_trail, _haversine
from api.org_permissions import get_user_organization, get_user_organization_or_none
from api.password import hash_device_password, verify_device_password
from api.throttles import DeviceScanThrottle, DeviceHeartbeatThrottle


def _deactivate_assignments(queryset):
    now = timezone.now()
    guard_ids = set(
        queryset.exclude(guard_supervisor=None)
        .values_list('guard_supervisor_id', flat=True)
    )
    queryset.update(is_active=False, ended_at=now)
    if guard_ids:
        active_guard_ids = set(
            ShiftAssignment.objects.filter(
                guard_supervisor_id__in=guard_ids, is_active=True
            ).values_list('guard_supervisor_id', flat=True)
        )
        inactive_guard_ids = guard_ids - active_guard_ids
        if inactive_guard_ids:
            GuardSupervisor.objects.filter(
                id__in=inactive_guard_ids, is_on_shift=True
            ).update(is_on_shift=False)


class ScanRecordViewSet(viewsets.ModelViewSet):
    serializer_class = ScanRecordSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_throttles(self):
        if self.action == 'create':
            return [DeviceScanThrottle()]
        return []

    def get_queryset(self):
        user = self.request.user
        queryset = ScanRecord.objects.select_related(
            'guard_supervisor', 'device', 'route', 'checkpoint'
        )

        if user.is_superuser or hasattr(user, 'admin_profile'):
            pass
        else:
            org = get_user_organization_or_none(user)
            if org:
                queryset = queryset.filter(
                    Q(guard_supervisor__organization=org) |
                    Q(device__organization=org) |
                    Q(route__organization=org)
                ).distinct()
            else:
                return ScanRecord.objects.none()

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        guard_id = self.request.query_params.get('guard_id')
        route_id = self.request.query_params.get('route_id')
        is_on_time = self.request.query_params.get('is_on_time')

        if start_date: queryset = queryset.filter(timestamp__date__gte=start_date)
        if end_date: queryset = queryset.filter(timestamp__date__lte=end_date)
        if guard_id: queryset = queryset.filter(guard_supervisor_id=guard_id)
        if route_id: queryset = queryset.filter(route_id=route_id)
        if is_on_time:
            queryset = queryset.filter(is_on_time=is_on_time.lower() == 'true')

        return queryset.order_by('-timestamp')

    def create(self, request, *args, **kwargs):
        client_ts_str = request.data.get('client_timestamp')
        client_timestamp = None
        if client_ts_str:
            try:
                client_timestamp = datetime.fromisoformat(client_ts_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                pass
        result = process_scan(
            device_id=request.data.get('device_id'),
            password=request.data.get('password'),
            route_id=request.data.get('route_id'),
            nfc_value=request.data.get('nfc_value'),
            peer_key=request.data.get('verification_key'),
            now=timezone.now(),
            raw_nfc=request.data.get('raw_nfc'),
            scan_lat=request.data.get('lat'),
            scan_lng=request.data.get('lng'),
            client_timestamp=client_timestamp,
            sequence_id=request.data.get('sequence_id'),
            sensor_context=request.data.get('sensor_context'),
        )
        extras = {
            'tts_message': result.pop('_tts_message', None),
            'tts_voice': result.pop('_tts_voice', 'en-US'),
            'tts_rate': result.pop('_tts_rate', 1.0),
            'tts_pitch': result.pop('_tts_pitch', 1.0),
            'play_sound': result.pop('_play_sound', True),
            'vibrate': result.pop('_vibrate', True),
            'map_update': result.pop('_map_update', None),
            'dropped': result.pop('_dropped', False),
        }
        if extras['dropped']:
            return Response({
                'status': 'dropped',
                'reason': result.get('verification_notes', 'out_of_tolerance_window'),
                'validity_score': 0.0,
            }, status=200)
        record = ScanRecord.objects.create(**result)
        data = ScanRecordSerializer(record).data
        data['tts_message'] = extras.get('tts_message')
        data['tts_voice'] = extras.get('tts_voice')
        data['tts_rate'] = extras.get('tts_rate')
        data['tts_pitch'] = extras.get('tts_pitch')
        data['play_sound'] = extras.get('play_sound', True)
        data['vibrate'] = extras.get('vibrate', True)
        data['out_of_sequence'] = result.get('out_of_sequence', False)
        data['insufficient_dwell_time'] = result.get('insufficient_dwell_time', False)
        data['dwell_seconds'] = result.get('dwell_seconds', None)
        data['time_drift_seconds'] = result.get('time_drift_seconds', None)
        data['dwell_valid'] = result.get('dwell_valid', False)
        data['anomaly_flags'] = result.get('anomaly_flags', [])
        data['sensor_aided'] = result.get('sensor_aided', False)
        data['map_update'] = extras.get('map_update')
        return Response(data, status=200)

    def perform_create(self, serializer):
        pass


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([DeviceScanThrottle])
def gps_batch_sync(request):
    device_id = request.data.get('device_id')
    password = request.data.get('password')
    points = request.data.get('points', [])

    if not device_id or not password:
        return Response({'detail': 'device_id and password required'}, status=400)
    if not isinstance(points, list) or not points:
        return Response({'detail': 'points array required'}, status=400)

    device = Device.objects.filter(device_id=device_id).first()
    if not device:
        return Response({'detail': 'Device not found'}, status=404)

    is_valid, needs_rehash = verify_device_password(password, device.password)
    if not is_valid:
        return Response({'detail': 'Auth failed'}, status=401)

    if needs_rehash:
        Device.objects.filter(id=device.id).update(password=hash_device_password(password))

    active_assignment = ShiftAssignment.objects.filter(device=device, is_active=True, is_completed=False).first()

    created = []
    raw_for_correction = []
    last_lat = None
    last_lng = None
    last_acc = None
    last_batt = None
    for p in points:
        recorded_at_str = p.get('recorded_at')
        if not recorded_at_str:
            continue
        try:
            recorded_at = datetime.fromisoformat(recorded_at_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            continue

        p_lat = p.get('lat')
        p_lng = p.get('lng')
        if p_lat is None or p_lng is None:
            continue

        trail = DeviceTrail.objects.create(
            device=device,
            assignment=active_assignment,
            lat=p_lat,
            lng=p_lng,
            accuracy=p.get('accuracy'),
            battery_pct=p.get('battery_pct'),
            speed=p.get('speed'),
            bearing=p.get('bearing'),
            recorded_at=recorded_at,
        )
        last_lat = trail.lat
        last_lng = trail.lng
        last_acc = trail.accuracy
        last_batt = trail.battery_pct

        created.append(trail.id)
        raw_for_correction.append({
            'lat': trail.lat,
            'lng': trail.lng,
            'accuracy': trail.accuracy or 50.0,
            'recorded_at': recorded_at,
        })

    if last_lat is not None:
        device.last_latitude = last_lat
        device.last_longitude = last_lng
        device.last_gps_accuracy = last_acc
        device.battery_pct = last_batt
        device.save(update_fields=['last_latitude', 'last_longitude', 'last_gps_accuracy', 'battery_pct'])

    corrected = correct_gps_trail(raw_for_correction)

    for i, corr in enumerate(corrected):
        if corr.get('corrected') and i < len(created):
            DeviceTrail.objects.filter(id=created[i]).update(
                lat=corr['lat'], lng=corr['lng'], is_corrected=True
            )

    return Response({
        'synced': len(created),
        'corrected': [{
            'lat': c['lat'],
            'lng': c['lng'],
            'accuracy': c.get('accuracy'),
            'recorded_at': c['recorded_at'].isoformat() if hasattr(c['recorded_at'], 'isoformat') else c['recorded_at'],
            'corrected': c.get('corrected', False),
        } for c in corrected],
    })


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([DeviceScanThrottle])
def scan_batch_sync(request):
    device_id = request.data.get('device_id')
    password = request.data.get('password')
    scans = request.data.get('scans', [])

    if not device_id or not password:
        return Response({'detail': 'device_id and password required'}, status=400)
    if not isinstance(scans, list) or not scans:
        return Response({'detail': 'scans array required'}, status=400)

    device = Device.objects.filter(device_id=device_id).first()
    if not device:
        return Response({'detail': 'Device not found'}, status=404)

    is_valid, needs_rehash = verify_device_password(password, device.password)
    if not is_valid:
        return Response({'detail': 'Auth failed'}, status=401)

    if needs_rehash:
        Device.objects.filter(id=device.id).update(password=hash_device_password(password))

    results = []
    for idx, s in enumerate(scans):
        nfc_value = s.get('nfc_value')
        recorded_at_str = s.get('recorded_at')
        if not nfc_value or not recorded_at_str:
            results.append({'_original_index': idx, 'status': 'skipped', 'reason': 'missing nfc_value or recorded_at'})
            continue
        try:
            recorded_at = datetime.fromisoformat(recorded_at_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            results.append({'_original_index': idx, 'status': 'skipped', 'reason': 'invalid recorded_at'})
            continue

        try:
            server_now = timezone.now()
            scan_data = process_scan(
                device_id, password,
                route_id=s.get('route_id'),
                nfc_value=nfc_value,
                peer_key=s.get('verification_key') or s.get('peer_key'),
                now=recorded_at,
                raw_nfc=s.get('raw_nfc'),
                scan_lat=s.get('lat'),
                scan_lng=s.get('lng'),
                client_timestamp=recorded_at,
                sequence_id=s.get('sequence_id'),
            )
            tts_msg = scan_data.pop('_tts_message', None)
            tts_v = scan_data.pop('_tts_voice', 'en-US')
            tts_r = scan_data.pop('_tts_rate', 1.0)
            tts_p = scan_data.pop('_tts_pitch', 1.0)
            ps = scan_data.pop('_play_sound', True)
            vb = scan_data.pop('_vibrate', True)
            scan_data.pop('_map_update', None)
            scan_data.pop('_dropped', None)
            scan_data['server_received_timestamp'] = server_now
            record = ScanRecord.objects.create(
                **{k: v for k, v in scan_data.items() if k != 'guard_supervisor'},
                guard_supervisor=scan_data['guard_supervisor'],
                timestamp=recorded_at,
            )
            results.append({'_original_index': idx, 'status': 'created', 'id': record.id, 'checkpoint': record.checkpoint_name,
                            'tts_message': tts_msg, 'tts_voice': tts_v, 'tts_rate': tts_r, 'tts_pitch': tts_p,
                            'play_sound': ps, 'vibrate': vb})
        except Exception as e:
            results.append({'_original_index': idx, 'status': 'error', 'reason': str(e)})

    return Response({'synced': len([r for r in results if r['status'] == 'created']), 'results': results})


@api_view(['GET'])
def device_trails(request, device_id):
    device = Device.objects.filter(device_id=device_id).first()
    if not device:
        return Response({'detail': 'Device not found'}, status=404)

    qs = DeviceTrail.objects.filter(device=device)

    assignment_id = request.GET.get('assignment_id')
    if assignment_id:
        qs = qs.filter(assignment_id=assignment_id)

    since = request.GET.get('since')
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            qs = qs.filter(recorded_at__gte=since_dt)
        except (ValueError, TypeError):
            pass

    qs = qs.order_by('recorded_at')

    points = list(qs.values('lat', 'lng', 'accuracy', 'recorded_at', 'battery_pct', 'speed', 'bearing', 'is_corrected'))

    if request.GET.get('corrected') == 'true' and len(points) > 1:
        raw = [{
            'lat': p['lat'],
            'lng': p['lng'],
            'accuracy': p['accuracy'] or 50.0,
            'recorded_at': p['recorded_at'],
        } for p in points]
        corrected = correct_gps_trail(raw)
        for i, c in enumerate(corrected):
            if i < len(points):
                points[i]['lat'] = c['lat']
                points[i]['lng'] = c['lng']
                points[i]['corrected'] = c.get('corrected', False)

    return Response({
        'device_id': device.device_id,
        'device_name': device.device_id or device.device_name,
        'point_count': len(points),
        'trail': points,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([DeviceScanThrottle])
def device_recent_scans(request):
    device_id = request.GET.get('device_id')
    password = request.GET.get('password')
    if not device_id or not password:
        return Response({'detail': 'device_id and password required'}, status=400)

    device = Device.objects.filter(device_id=device_id).first()
    if not device:
        return Response({'detail': 'Device not found'}, status=404)

    is_valid, needs_rehash = verify_device_password(password, device.password)
    if not is_valid:
        return Response({'detail': 'Auth failed'}, status=401)

    if needs_rehash:
        Device.objects.filter(id=device.id).update(password=hash_device_password(password))

    scans = ScanRecord.objects.filter(device=device).order_by('-timestamp')[:10]
    data = []
    for s in scans:
        data.append({
            'id': s.id,
            'checkpoint_name': s.checkpoint_name,
            'timestamp': s.timestamp.isoformat(),
            'is_on_time': s.is_on_time,
            'route_name': s.route.name if s.route else None,
        })
    return Response({'results': data})
