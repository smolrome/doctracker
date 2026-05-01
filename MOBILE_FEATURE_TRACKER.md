# Mobile App Feature Tracker

> DepEd Document Tracker — Web vs Mobile Parity Checklist
> Last updated: 2026-05-01 (updated after lower-priority + client portal sprint)

Legend: ✅ Done | 🚧 Partial | ❌ Missing | ⏭️ Skip (desktop-only / out of scope)

---

## 🔐 Authentication

| Feature | Status | Notes |
|---|---|---|
| Staff login | ✅ Done | `app/(auth)/login.tsx` |
| JWT token refresh | ✅ Done | `lib/api.ts` auto-refresh |
| Logout | ✅ Done | Profile screen |
| Client portal login | ⏭️ Skip | Separate user base, web-only |
| Client self-registration | ⏭️ Skip | Web-only |

---

## 📄 Documents — Core CRUD

| Feature | Status | Notes |
|---|---|---|
| List documents (search + filter) | ✅ Done | `app/(app)/documents/index.tsx` |
| View document detail | ✅ Done | `app/(app)/documents/[id].tsx` |
| Add document (full form) | ✅ Done | Bottom sheet modal in `_layout.tsx` (FAB `+` button) |
| Edit document fields | ✅ Done | Full edit modal in `[id].tsx` (admin + staff) |
| Delete document (admin) | ✅ Done | `[id].tsx` — admin only (soft delete → trash) |
| Restore from trash | ✅ Done | `app/(app)/trash.tsx` — Restore button |
| View trash / manage deleted docs | ✅ Done | `app/(app)/trash.tsx` — accessible from Profile |
| Permanent delete | ✅ Done | `app/(app)/trash.tsx` — admin only |
| Empty all trash | ✅ Done | "Empty All" button in trash header (admin) |
| Bulk status update | ✅ Done | Long-press to enter bulk mode, tap Status in action bar |
| Bulk delete | ✅ Done | Long-press to enter bulk mode, tap Delete (admin) |
| CSV / export | ⏭️ Skip | Desktop-only feature |
| Duplicate check | ✅ Done | API call on add form (once built) |

---

## 📊 Dashboard & Stats

| Feature | Status | Notes |
|---|---|---|
| Dashboard overview (stats cards) | ✅ Done | `app/(app)/dashboard.tsx` |
| Recent documents list | ✅ Done | Dashboard screen |
| Staff statistics | ✅ Done | `app/(app)/staff-stats.tsx` |
| Office documents view | ✅ Done | `app/(app)/office-docs.tsx` — grouped by office, tap to filter |

---

## 📬 Receive / Transfer / Routing

| Feature | Status | Notes |
|---|---|---|
| Receive pending documents | ✅ Done | `app/(app)/receive-docs.tsx` |
| Accept document | ✅ Done | Accept button on receive-docs |
| Reject document | ✅ Done | Reject with reason on receive-docs |
| Transfer document to staff | ✅ Done | Transfer modal in `[id].tsx` (staff + admin) |
| View routing slips list | ✅ Done | `app/(app)/routing-slips.tsx` |
| View routing slip detail | ✅ Done | `app/(app)/routing-slip-detail.tsx` — tap a slip to open |
| Create routing slip | ✅ Done | "Create Routing Slip" button on `[id].tsx` (staff + admin) |
| Create grouped routing slip | ⏭️ Skip | Single-doc slip covers mobile use case |
| Reroute document | ✅ Done | "Reroute Slip" in `routing-slip-detail.tsx` |
| Archive routing slip | ✅ Done | Archive button in `routing-slip-detail.tsx` (admin) |
| Batch status update on slip | ✅ Done | "Batch Update Status" in `routing-slip-detail.tsx` |

---

## 📷 QR Code & Scanning

| Feature | Status | Notes |
|---|---|---|
| Live camera QR scan | ✅ Done | `app/(app)/scanner.tsx` |
| Upload QR from gallery | 🚧 Partial | Code done; needs `npx expo run:android` rebuild |
| View document QR code | ✅ Done | `[id].tsx` QR section |
| Download / share QR image | ✅ Done | `[id].tsx` Download button |
| Torch toggle | ✅ Done | Scanner screen |
| Office action scanning | ⏭️ Skip | Web-only office workflow |
| Slip scan integration | ❌ Missing | Scan routing slip QR |

---

## 👤 User Profile

| Feature | Status | Notes |
|---|---|---|
| View profile info | ✅ Done | `app/(app)/profile.tsx` |
| Edit display name & office | ✅ Done | Profile screen |
| Change password | ✅ Done | Profile screen |
| View role / username (read-only) | ✅ Done | Profile screen |

---

## 🔔 Notifications

| Feature | Status | Notes |
|---|---|---|
| Push notification registration | ✅ Done | `lib/notifications.ts` |
| Notification history screen | ✅ Done | `app/(app)/notifications.tsx` |

---

## 📋 Activity Log

| Feature | Status | Notes |
|---|---|---|
| View activity log | ✅ Done | `app/(app)/activity-log.tsx` |

---

## 🛡️ Admin Features

| Feature | Status | Notes |
|---|---|---|
| List all users | ✅ Done | `app/(app)/admin-users.tsx` |
| Create user | ✅ Done | Admin users screen |
| Edit user (name, role, office) | ✅ Done | Admin users screen |
| Activate / deactivate user | ✅ Done | Admin users screen |
| Delete user | ✅ Done | Admin users screen |
| Approve pending user | ✅ Done | Admin users screen |
| Reset user password | ✅ Done | Admin users screen |
| Pending clients approval queue | ✅ Done | `app/(app)/pending-clients.tsx` — approve / reject |
| Assign document to staff | ✅ Done | API `POST /documents/<id>/assign` + `[id].tsx` assign modal |
| Unassign document from staff | ✅ Done | API `POST /documents/<id>/unassign` |
| Manage dropdown options | ✅ Done | `app/(app)/dropdown-options.tsx` — edit + reset |
| Bulk user import (Excel) | ⏭️ Skip | Desktop-only |
| Send invite email | ⏭️ Skip | Desktop-only |
| Database tools / clear DB | ⏭️ Skip | Admin utility, web-only |

---

## 🌐 Client Portal (Mobile — `app/(client)/`)

| Feature | Status | Notes |
|---|---|---|
| Client registration | ✅ Done | `app/(auth)/register.tsx` — public sign-up form |
| Client login + role redirect | ✅ Done | `login.tsx` routes client → `/(client)/my-docs` |
| Client tab layout | ✅ Done | `app/(client)/_layout.tsx` — My Docs / Submit / Trash / Profile |
| Client document list | ✅ Done | `app/(client)/my-docs.tsx` — search + filter |
| Submit document | ✅ Done | `app/(client)/submit.tsx` — category picker + success screen |
| Track document | ✅ Done | `app/(client)/track/[id].tsx` — status + travel log |
| Client trash & restore | ✅ Done | `app/(client)/trash.tsx` — restore + permanent delete |
| Client profile | ✅ Done | `app/(client)/profile.tsx` — edit name + change password |

---

## 📶 Offline / Network

| Feature | Status | Notes |
|---|---|---|
| Offline banner indicator | ✅ Done | `components/ui/OfflineBanner.tsx` |
| Offline cache for docs | ✅ Done | `lib/cache.ts` |
| Cache clear from profile | ✅ Done | Profile screen |

---

## 🗂️ Build & Infrastructure

| Feature | Status | Notes |
|---|---|---|
| Expo Dev Client setup | ✅ Done | Bare workflow |
| `expo-image-picker` native module | ❌ Needs rebuild | Run `npx expo run:android` once (needs Android Studio) |
| System status / DB health | ✅ Done | `app/(app)/db-status.tsx` — admin only |
| Android SDK / ANDROID_HOME set up | ❌ Needs setup | Install Android Studio first |
| Production API connected | ✅ Done | `https://doctracker.depedleytepersonnelunit.com` |

---

## 🎯 Suggested Build Order (next features)

1. ✅ **Add Document form** — built into `_layout.tsx` bottom sheet
2. ✅ **Transfer Document UI** — transfer modal on `[id].tsx`
3. ✅ **Routing Slip detail screen** — `routing-slip-detail.tsx`, tap a slip to open
4. ✅ **Trash screen** — `trash.tsx`, accessible from Profile (admin)
5. ❌ **Upload QR from gallery** — do `npx expo run:android` rebuild first
6. ✅ **Create Routing Slip** — green button on document detail screen
7. ✅ **Reroute Slip** — in routing slip detail screen
8. ✅ **Batch Status Update** — in routing slip detail screen
9. ❌ **Office Documents view** — filter docs by office (admin)
10. ❌ **Assign document to staff** — admin assign/unassign
