import api from '../api';
import { QRResponse, QRScanResponse, Document } from '../types';

export const qrService = {
  async generateQR(docId: string): Promise<QRResponse> {
    const response = await api.get<QRResponse>(`/qr/generate/${docId}`);
    return response.data;
  },

  async scanQR(token: string): Promise<QRScanResponse> {
    const response = await api.post<QRScanResponse>('/qr/scan', { token });
    return response.data;
  },
};

export default qrService;