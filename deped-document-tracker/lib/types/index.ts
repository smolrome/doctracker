export interface User {
  id: string;
  full_name: string;
  role: 'admin' | 'staff' | 'client' | 'viewer';
  office: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: User;
}

export interface Document {
  id: string;
  ref?: string;
  subject: string;
  type: string;
  office: string;
  status: string;
  created_at?: string;
  logged_by?: string;
  [key: string]: any;
}

export interface DocumentsResponse {
  documents: Document[];
  total: number;
  page: number;
  limit: number;
}

export interface Stats {
  total: number;
  logged: number;
  pending: number;
  received: number;
  in_review: number;
  routed: number;
  transferred: number;
  released: number;
  on_hold: number;
  archived: number;
  unknown: number;
  staff: number;
  client: number;
}

export interface Office {
  office_name: string;
  office_slug: string;
  created_by: string;
  primary_recipient?: string;
}

export interface RoutingSlip {
  id: string;
  slip_no: string;
  from_office: string;
  to_office: string;
  status: string;
  created_at: string;
}

export interface ActivityLog {
  id: string;
  action: string;
  detail: string;
  username: string;
  ip?: string;
  timestamp: string;
}

export interface DropdownOptions {
  [field: string]: string[];
}

export interface QRResponse {
  doc_id: string;
  qr_base64: string;
}

export interface QRScanResponse {
  doc: Document;
  token_type: string;
}

export interface RoutingEntry {
  from_office: string;
  to_office: string;
  status: string;
  remarks: string;
  timestamp: string;
  updated_by: string;
}