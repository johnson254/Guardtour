"""
Thin backward-compatible re-export module.
All logic has been moved to api/services/ submodules.
"""
from api.services.gps import _haversine, _spherical_interpolate, correct_gps_trail
from api.services.drift import validate_timestamp_drift, validate_sequence_id
from api.services.dwell import _walk_dwell_trail, check_dwell_time
from api.services.anomalies import _detect_anomalies, _sensor_confirms_presence, _sensor_mismatch
from api.services.scoring import (
    verify_zone_scan,
    _compute_effective_radius,
    _tolerance_window,
    device_has_clean_progression_record,
    calculate_scan_validity,
)
from api.services.fallback import apply_sensor_fallback
from api.services.scan import (
    authenticate_device,
    check_cooldown,
    parse_nfc_payload,
    validate_peer_exchange,
    resolve_asset,
    resolve_assignment,
    is_on_time,
    check_sequence,
    trigger_emergency,
    route_gap_analysis,
    get_mission_status,
    transfer_shift,
    process_scan,
)

MAX_TIMESTAMP_DRIFT_SECONDS = 300
PRECISION_MULTIPLIER = {'strict': 0.5, 'normal': 1.0, 'loose': 2.0}
MAX_HUMAN_WALKING_SPEED_M_PER_MIN = 120
GPS_INSTABILITY_HDOP_THRESHOLD = 6.0
GPS_STABLE_HDOP_THRESHOLD = 3.0
DRIFT_SPEED_M_PER_S = 0.5
PROLONGED_DWELL_MULTIPLIER = 2.5
