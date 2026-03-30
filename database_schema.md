# PostgreSQL Database Schema - Document Tracker

## Tables

### 1. documents
Primary document storage using JSONB for flexible schema.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | Unique document identifier |
| data | JSONB | NOT NULL | Document content and metadata |
| created_at | TIMESTAMP | DEFAULT NOW() | Creation timestamp |

**Indexes:**
- `idx_documents_created` ON `created_at DESC`

---

### 2. users
User accounts and authentication.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-incrementing user ID |
| username | TEXT | UNIQUE, NOT NULL | Login username |
| password_hash | TEXT | NOT NULL | Bcrypt hashed password |
| full_name | TEXT | | User's full name |
| role | TEXT | DEFAULT 'staff' | User role (staff/admin) |
| office | TEXT | DEFAULT '' | Assigned office |
| active | BOOLEAN | DEFAULT TRUE | Account active status |
| last_login | TIMESTAMP | | Last login timestamp |
| approved | BOOLEAN | DEFAULT TRUE | Admin approval status |
| created_at | TIMESTAMP | DEFAULT NOW() | Creation timestamp |

---

### 3. invite_tokens
Invitation tokens for new user registration.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| token | TEXT | PRIMARY KEY | Unique invitation token |
| email | TEXT | NOT NULL | Invitation email address |
| name | TEXT | | Invited user's name |
| used | BOOLEAN | DEFAULT FALSE | Token used status |
| created_at | TIMESTAMP | DEFAULT NOW() | Token creation time |
| expires_at | TIMESTAMP | DEFAULT (NOW() + 48h) | Token expiration time |

---

### 4. office_qr_codes
QR codes for office-related actions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | Unique QR code identifier |
| action | TEXT | NOT NULL | QR code action type |
| label | TEXT | | Human-readable label |
| created_at | TIMESTAMP | DEFAULT NOW() | Creation timestamp |

---

### 5. saved_offices
Office configurations and settings.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| office_slug | TEXT | PRIMARY KEY | URL-friendly office identifier |
| office_name | TEXT | NOT NULL | Display name of office |
| created_by | TEXT | | User who created the office |
| primary_recipient | TEXT | | Primary contact/recipient |
| created_at | TIMESTAMP | DEFAULT NOW() | Creation timestamp |

---

### 6. activity_log
Audit trail of user actions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Log entry ID |
| username | TEXT | | User who performed action |
| action | TEXT | NOT NULL | Action type/description |
| ip_address | TEXT | | Client IP address |
| detail | TEXT | | Additional details |
| ts | TIMESTAMP | DEFAULT NOW() | Timestamp |

**Indexes:**
- `idx_activity_log_user` ON `username`
- `idx_activity_log_ts` ON `ts DESC`

---

### 7. routing_slips
Document routing slips for tracking movement.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | Unique slip identifier |
| slip_no | TEXT | NOT NULL | Routing slip number |
| destination | TEXT | NOT NULL | Destination office |
| prepared_by | TEXT | | User who prepared slip |
| doc_ids | JSONB | NOT NULL | Array of document IDs |
| notes | TEXT | | Additional notes |
| slip_date | TEXT | | Date of slip |
| time_from | TEXT | | Start time |
| time_to | TEXT | | End time |
| from_office | TEXT | | Originating office |
| recv_token | TEXT | | Receive token |
| rel_token | TEXT | | Release token |
| type | TEXT | DEFAULT 'routing' | Slip type |
| logged_at | TEXT | | Log timestamp |
| status | TEXT | DEFAULT 'Routed' | Current status |
| is_rerouted | BOOLEAN | DEFAULT FALSE | Reroute flag |
| archived_at | TEXT | | Archive timestamp |
| archived_by | TEXT | | User who archived |
| rerouted_to | TEXT | | New destination |
| original_slip_id | TEXT | | Original slip ID (for reroutes) |
| original_slip_no | TEXT | | Original slip number |
| rerouted_from | TEXT | | Original destination |
| created_at | TIMESTAMP | DEFAULT NOW() | Creation timestamp |

---

### 8. office_traffic
Office entry/exit tracking.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Traffic record ID |
| office_slug | TEXT | NOT NULL | Office identifier |
| office_name | TEXT | NOT NULL | Office display name |
| event_type | TEXT | NOT NULL | Event type |
| doc_id | TEXT | | Related document ID |
| client_username | TEXT | | Client username |
| scanned_at | TIMESTAMP | DEFAULT NOW() | Scan timestamp |

---

### 9. doc_qr_tokens
QR tokens for document actions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| token | TEXT | PRIMARY KEY | Unique token |
| doc_id | TEXT | NOT NULL | Associated document ID |
| token_type | TEXT | NOT NULL | Token action type |
| used | BOOLEAN | DEFAULT FALSE | Token used status |
| created_at | TIMESTAMP | DEFAULT NOW() | Creation timestamp |

---

### 10. dropdown_options
Customizable dropdown options for document types.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Option ID |
| field_name | TEXT | UNIQUE, NOT NULL | Field identifier |
| options | JSONB | NOT NULL, DEFAULT '[]' | Array of options |
| created_at | TIMESTAMP | DEFAULT NOW() | Creation timestamp |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last update timestamp |

---

## Indexes Summary

| Index Name | Table | Column(s) | Type |
|------------|-------|-----------|------|
| idx_activity_log_user | activity_log | username | B-tree |
| idx_activity_log_ts | activity_log | ts | B-tree (DESC) |
| idx_documents_created | documents | created_at | B-tree (DESC) |

---

## Entity Relationship Summary

```
users ─────┬───── invite_tokens (created_by)
           │
           └───── activity_log (username)
           
saved_offices ────── office_traffic (office_slug)
           │
           └───── office_qr_codes

documents ────── doc_qr_tokens (doc_id)
           │
           └───── routing_slips (via doc_ids JSONB)

routing_slips ────── office_traffic (destination)
```