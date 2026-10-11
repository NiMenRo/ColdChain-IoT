# Notifications Module

Internal alert management for the dashboard + persistent multi-channel
delivery records (Fase A/B).

## Channels

| Channel   | Adapter               | Result when idle/misconfigured | Real delivery? |
|-----------|-----------------------|-------------------------------|----------------|
| dashboard | `DashboardNotificationChannel` (in-app) | `SENT` | Yes (in-app record) |
| email     | `SmtpEmailChannel` (optional real SMTP) | `DISABLED` | Only with `SMTP_ENABLED=true` + host/from; transport errors → `FAILED` |
| sms       | `LoggingSmsChannel` (simulated) | `SIMULATED` (or `DISABLED` if `SMS_SIMULATED=false`) | **Never** — log + persisted row only |
| push      | `DecoupledPushChannel` (Web Push NOT implemented) | `DISABLED` (or `SIMULATED` if `PUSH_ENABLED=true`) | **Never** |

Status semantics: `pending` = prepared, not attempted; `sent` = transport
confirmed a real delivery; `failed` = attempted and rejected; `simulated` =
explicitly simulated, recorded for traceability, never a real send;
`disabled` = channel not configured, no attempt made. Simulated/disabled
rows are never reported as sent (`NotificationProcessResult.succeeded` is
`SENT`-only; `completed` covers finished-without-internal-error).

Legacy prototype adapters (`Email/SMS/PushNotificationChannel` as pure
in-memory `SENT` recorders) are preserved untouched for existing tests;
production wires `production_channels()` from environment (see
`channel_config.py` + `backend/.env.example`). Secrets (`SMTP_PASSWORD`)
go only to the SMTP transport — never to logs, results, or `detail`.

## Persistence & transactions (explicit contract)

- `NotificationORM` (`notifications` table, Alembic `e8b2c4d6a1f3`):
  `alert_id → alerts`, `user_id → users`, `channel`, `status`,
  `is_read`/`read_at` (default unread), `recipient`, `message`, `detail`,
  `notification_date`. `UNIQUE(alert_id, channel, recipient)` = idempotency
  key. Migration is fully additive (no backfill, no data changes).
- `UserORM.phone` (nullable): optional SMS contact. `NULL` falls back to a
  logged placeholder recipient; still `SIMULATED`, never sent.
- `NotificationRepository`: flush-only, like every repository — the caller
  owns commit/rollback.
- `NotificationService.process()`: send-only, never raises on
  channel/transport failures (recorded on the result).
- `NotificationService.process_and_persist(alert, db, ...)`: idempotent
  (duplicate → existing row, no resend, unless `force=True`); flush-only,
  except a unique-race `IntegrityError` where it rolls back only its own
  flush and returns the winner. Callers must isolate notification
  persistence in its own transaction.
- Acquisition pipeline (`app/acquisition/pipeline.py`): sends during event
  handling (non-blocking), then persists rows in a SEPARATE transaction
  after the bundle commits. A notification failure therefore only loses
  traceability rows (logged) — alerts and readings are never rolled back.
  An SMTP outage never blocks the pipeline and never loses an alert.

## Read state vs acknowledgement

`is_read`/`read_at` are independent from `Alert.acknowledged`: reading a
notification never acknowledges its alert, and acknowledging an alert never
marks its notifications as read.

## Read API (Fase C, owner-scoped)

- `GET /notifications/persistent` — durable history of the authenticated
  user only (default limit 50, max 200), filters `status` / `channel` /
  `alert_id` / `is_read`, newest first, with linked alert summaries.
- `GET /notifications/unread-count` — `{unread}` for the bell badge.
- `PATCH /notifications/{id}/read` — mark one owned row read (idempotent;
  foreign/unknown ids answer 404 to avoid existence oracles).
- `POST /notifications/read-all` — mark all owned rows read (`{updated}`).
- All endpoints require authentication; every human role may use them on
  its own rows. The volatile runtime `GET /notifications/history` prototype
  is preserved unchanged for backward compatibility.

## Failure matrix: alert committed, notification failed (Fase C)

Each layer owns exactly one transaction, so failures stay local:

| Failure point | What survives | What is lost | Retry duplicates? |
|---|---|---|---|
| Channel/send fails (SMTP down, bad recipient) | Alert row + in-memory notification with `FAILED`/`DISABLED` status | Nothing (outcome recorded) | No — same key returns existing row |
| Pipeline notification-persist block fails | Bundle already committed (readings + alerts durable) | Traceability rows of that batch (logged) | No — dedup key blocks re-persist; sends already happened once |
| `POST /process` DB unreachable | In-memory mirror only | Durable row (503/400 surfaces it) | No — next attempt finds no row and processes once |
| Unique race (concurrent duplicate) | Winner row | Loser's flush only (isolated tx) | No — loser returns the winner |

Recovery without a retry system (deliberately manual, audited):

1. `POST /notifications/process` with `{"alert_id": "..."}` replays a
   missing delivery: if the alert left runtime memory (restart), the
   endpoint rebuilds it from the durable `alerts` row preserving the
   original owner; if a row already exists it returns it with
   `duplicate: true` and does NOT re-send.
2. `POST /notifications/process` with `{"alert_id": "...", "force": true}`
   redispatches a `failed`/`disabled`/`pending` row: the delivery is
   attempted again and the SAME row adopts the new outcome
   (`redelivered: true`, audited as `notification.redispatch`). Already
   `sent`/`simulated` rows answer 409 and are never re-sent nor rewritten.
3. No daemon, no queue, no backoff: redispatch is an explicit admin action
   for exceptional cases, not a background mechanism.

## Recipient policy: fan-out to active supervising humans

Pipeline notifications fan out to every active (`is_active=True`) human user
with a supervising role (`admin`, `supervisor`, `operador`, `auditor`),
one row per (alert × recipient). Rationale per `USER_ROLE_RESPONSIBILITIES`
and `context/Matriz_RBAC.md`:

- `supervisor`/`operador`/`admin` need operational awareness (ack duty,
  escalation, redispatch); `auditor` receives read-only rows for
  supervision/traceability — receiving rows grants no write power.
- Excluded: `system` (technical identity, no login/HTTP) and inactive users.
- No RBAC/matrix change was needed: all Fase C read endpoints already use
  `authenticated` (all human roles); `require_ack` (ack),
  `require_notification_write` (delivery status) and `require_admin`
  (process/redispatch) are untouched, so the auditor stays 403 there.
- Isolation unchanged: `user_id` = recipient owner, endpoints filter by
  token id, foreign ids answer 404. No duplicates: existing
  `UNIQUE(alert_id, channel, recipient)` + per-row `find_duplicate` check
  inside the already-isolated transaction.
- Channel routing unchanged (default dashboard → `sent` in-app). Per-channel
  recipient: dashboard/push → user id string; email → user email; sms →
  user phone or `user:{id}` fallback (still `SIMULATED`, logged, never sent).
- Manual `POST /process` stays single-owner (admin's own record + audit):
  no automatic fan-out on manual actions.
- Legacy fallback: if no human recipients exist in DB, one row owned by the
  alert author is kept (previous behavior).
- Pre-existing `system`-owned rows are NOT backfilled; only new alerts
  distribute.
