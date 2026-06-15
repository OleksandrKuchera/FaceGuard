// ── Auth ────────────────────────────────────────────────────────────────────
export type SystemRole = 'superadmin' | 'admin' | 'guard' | 'readonly';

export interface User {
  username: string;
  role: SystemRole;
  first_name: string;
  last_name: string;
}

export interface SystemUser {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  role: SystemRole;
  is_active: boolean;
  date_joined: string;
}

// ── Department ───────────────────────────────────────────────────────────────
export interface Department {
  id: number;
  name: string;
  code: string;
}

// ── Person ───────────────────────────────────────────────────────────────────
export type PersonRole = 'staff' | 'visitor' | 'contractor' | 'unknown';

export interface Person {
  id: number;
  first_name: string;
  last_name: string;
  middle_name?: string;
  full_name: string;
  person_id: string;
  role: PersonRole;
  department?: number;
  department_name?: string;
  access_level: number;
  is_active: boolean;
  primary_photo?: string;
  notes?: string;
  consent_given?: boolean;
  consent_date?: string | null;
  deletion_requested?: boolean;
  created_at: string;
  updated_at: string;
}

export interface PersonPhoto {
  id: number;
  person: number;
  image: string;
  is_processed: boolean;
  face_detected: boolean | null;
  quality_score: number | null;
  uploaded_at: string;
}

export interface TrainStatus {
  encodings_created: number;
  photos_processed: number;
  photos_failed: number;
  total_photos: number;
  best_quality_score: number | null;
  task_id: string | null;
  task_state: 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | null;
  is_ready: boolean;
}

// ── Camera ───────────────────────────────────────────────────────────────────
export type CameraStatus = 'active' | 'offline' | 'maintenance';

export interface Camera {
  id: number;
  name: string;
  location: string;
  camera_code: string;
  stream_url: string;
  is_local: boolean;
  status: CameraStatus;
  last_ping?: string;
  recognition_enabled: boolean;
  detection_confidence: number;
  frame_skip: number;
  resolution_scale: number;
  access_zone?: string;
  requires_mfa: boolean;
  created_at: string;
}

// ── Events ───────────────────────────────────────────────────────────────────
export type EventType = 'recognized' | 'unknown' | 'spoofing' | 'multi_face' | 'low_quality';

export interface RecognitionEvent {
  id: number;
  camera: { id: number; name: string; location: string };
  person: { id: number; full_name: string; person_id: string; role: PersonRole } | null;
  person_display?: string;
  event_type: EventType;
  event_type_display?: string;
  confidence: number | null;
  distance: number | null;
  liveness_score: number | null;
  frame_snapshot: string | null;
  face_crop: string | null;
  face_bbox_json: { top: number; right: number; bottom: number; left: number } | null;
  timestamp: string;
  processed_at: string;
  is_alert: boolean;
  alert_sent: boolean;
  spoofing_meta?: {
    attack_type: AttackType;
    attack_type_display: string;
    ear_value: number | null;
    texture_score: number | null;
    detected_at: string;
  } | null;
  reviewed_by: number | null;
  reviewed_at: string | null;
}

export interface EventStats {
  today: number;
  recognized: number;
  unknown: number;
  spoofing: number;
  alerts: number;
  total?: number;
}

export interface DailyStat {
  date: string;
  recognized: number;
  unknown: number;
  spoofing_attempts: number;
  total_events: number;
  unique_persons: number;
}

// ── Reports ──────────────────────────────────────────────────────────────────
export type ReportType = 'attendance' | 'unknown_persons' | 'security_audit' | 'daily_summary' | 'custom';
export type ReportFormat = 'pdf' | 'csv' | 'xlsx';
export type ReportStatus = 'pending' | 'generating' | 'ready' | 'failed';

export interface Report {
  id: number;
  name: string;
  report_type: ReportType;
  format: ReportFormat;
  params_json: Record<string, unknown>;
  file?: string;
  download_url?: string;
  status: ReportStatus;
  error_message?: string;
  created_by_name?: string;
  created_at: string;
  generated_at?: string;
}

// ── Security ─────────────────────────────────────────────────────────────────
export type AttackType = 'photo' | 'video' | 'unknown';

export interface SpoofingAttempt {
  id: number;
  camera_name: string;
  event: number;
  attack_type: AttackType;
  ear_value: number | null;
  texture_score: number | null;
  frame_evidence: string | null;
  detected_at: string;
  ip_address: string | null;
}

export interface AuditLog {
  id: number;
  username?: string;
  action: string;
  resource_type: string;
  resource_id: string;
  ip_address: string | null;
  timestamp: string;
}

export interface SecurityStats {
  total_spoofing: number;
  photo_attacks: number;
  video_attacks: number;
  last_24h: number;
}

// ── Pagination ───────────────────────────────────────────────────────────────
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── WebSocket ────────────────────────────────────────────────────────────────
export interface WsFace {
  bbox: { top: number; right: number; bottom: number; left: number };
  person_id: number | null;
  person_name: string | null;
  confidence: number | null;
  distance?: number | null;
  is_known: boolean;
  is_spoofing: boolean;
  is_warming_up: boolean;
  is_in_cooldown?: boolean;
  liveness_state?: 'IDLE' | 'WARMING_UP' | 'LIVE' | 'LIVENESS_FAILED' | 'INSUFFICIENT_DATA' | 'COOLDOWN';
  liveness_reason?: string;
  final_status?: 'IDLE' | 'WARMING_UP' | 'LIVE' | 'LIVENESS_FAILED' | 'INSUFFICIENT_DATA' | 'COOLDOWN' | 'SPOOF';
  final_reason_code?: string;
  final_module_name?: string;
  liveness_score?: number;
  texture_score: number;
  texture_is_spoof?: boolean;
  liveness_is_spoofing?: boolean;
  track_id?: number | null;
  landmarks?: Record<string, [number, number][]>;
  debug_enabled?: boolean;
  blink_count?: number | null;
  min_blinks_required?: number | null;
  blink_liveness_status?: 'PASS' | 'FAIL' | 'UNKNOWN' | 'WARMING_UP' | 'COLLECTING_BASELINE' | 'WATCHING_FOR_BLINK' | null;
  eye_state?: 'open' | 'closed' | 'unknown' | string | null;
  current_ear_left?: number | null;
  current_ear_right?: number | null;
  current_ear_avg?: number | null;
  smoothed_ear?: number | null;
  open_eye_baseline?: number | null;
  drop_ratio?: number | null;
  recovery_ratio?: number | null;
  blink_down_threshold?: number | null;
  blink_recovery_threshold?: number | null;
  baseline_buffer_size?: number | null;
  baseline_required_frames?: number | null;
  baseline_ready?: boolean | null;
  baseline_state?: 'COLLECTING' | 'READY' | 'FAILED' | string | null;
  previous_eye_state?: string | null;
  blink_internal_state?: 'BASELINE_COLLECTING' | 'BLINK_DETECTION_ACTIVE' | 'BLINK_PASSED' | string | null;
  blink_event_detected_this_frame?: boolean | null;
  blink_event_history?: string[] | null;
  last_blink_event_time?: number | null;
  min_ear_seen_during_warmup?: number | null;
  max_ear_seen_during_warmup?: number | null;
  blink_reason_code?: string | null;
  frames_closed_count?: number | null;
  frames_open_count?: number | null;
  valid_ear_frames_count?: number | null;
  missing_landmarks_count?: number | null;
  warmup_elapsed_seconds?: number | null;
  warmup_remaining_seconds?: number | null;
  cooldown_remaining_seconds?: number | null;
  texture_combined_status?: 'PASS' | 'FAIL' | 'UNKNOWN' | null;
  texture_lbp_status?: 'PASS' | 'FAIL' | 'UNKNOWN' | null;
  texture_sobel_status?: 'PASS' | 'FAIL' | 'UNKNOWN' | null;
  texture_fft_status?: 'PASS' | 'FAIL' | 'UNKNOWN' | null;
  face_quality_status?: 'PASS' | 'FAIL' | 'UNKNOWN' | null;
  blink_detector_called?: boolean | null;
  landmarks_found?: boolean | null;
  debug_hint?: string | null;
  debug?: Record<string, unknown> | null;
  event_id?: number | null;
}

export interface WsFrameMessage {
  type: 'frame';
  camera_id: number;
  timestamp: string;
  frame: string;
  faces: WsFace[];
  fps: number;
}

export interface WsAlertMessage {
  type: 'alert';
  alert_level: 'low' | 'medium' | 'high';
  message: string;
  camera_id: number;
  event_id: number;
  timestamp: string;
}

export interface WsCameraStatusMessage {
  type: 'camera_status';
  camera_id: number;
  status: CameraStatus;
  message: string;
}

export type WsMessage = WsFrameMessage | WsAlertMessage | WsCameraStatusMessage;
