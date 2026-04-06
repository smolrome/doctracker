import api from '../api';
import { Document, DocumentsResponse, Stats } from '../types';

export const documentService = {
  async getDocuments(params?: {
    status?: string;
    office?: string;
    search?: string;
    page?: number;
    limit?: number;
  }): Promise<DocumentsResponse> {
    const response = await api.get<DocumentsResponse>('/documents', { params });
    return response.data;
  },

  async getDocument(id: string): Promise<Document> {
    const response = await api.get<Document>(`/documents/${id}`);
    return response.data;
  },

  async createDocument(data: {
    subject: string;
    type: string;
    office: string;
  }): Promise<Document> {
    const response = await api.post<Document>('/documents', data);
    return response.data;
  },

  async updateDocumentStatus(
    id: string,
    status: string,
    remarks?: string
  ): Promise<Document> {
    const response = await api.patch<Document>(`/documents/${id}/status`, {
      status,
      remarks,
    });
    return response.data;
  },

  async deleteDocument(id: string): Promise<void> {
    await api.delete(`/documents/${id}`);
  },

  async getStats(): Promise<Stats> {
    const response = await api.get<Stats>('/stats');
    return response.data;
  },
};

export default documentService;