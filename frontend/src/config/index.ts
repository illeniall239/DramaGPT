// API Configuration
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// API Endpoints
export const API_ENDPOINTS = {
  // Workspace endpoints (legacy - for compatibility)
  upload: `${API_BASE_URL}/api/upload`,
  query: `${API_BASE_URL}/api/query`,
  generateReport: `${API_BASE_URL}/api/generate-report`,
  cancelOperation: `${API_BASE_URL}/api/cancel-operation`,
  resetState: `${API_BASE_URL}/api/reset-state`,
  learnProgress: (workspaceId: string) => `${API_BASE_URL}/api/workspace/${workspaceId}/learn/progress`,
  learnDatasets: `${API_BASE_URL}/api/learn/datasets`,
  learnPracticeChallenge: `${API_BASE_URL}/api/learn/practice-challenge`,
  learnQuery: `${API_BASE_URL}/api/learn/query`,

  // Knowledge Base endpoints
  KB: {
    CREATE: `${API_BASE_URL}/api/kb/create`,
    LIST: `${API_BASE_URL}/api/kb/list`,
    DELETE: (kbId: string) => `${API_BASE_URL}/api/kb/${kbId}`,
    UPLOAD: (kbId: string) => `${API_BASE_URL}/api/kb/${kbId}/upload`,
    QUERY: (kbId: string) => `${API_BASE_URL}/api/kb/${kbId}/query`,
    PREDICT: (kbId: string) => `${API_BASE_URL}/api/kb/${kbId}/predict`,
    DOCUMENTS: (kbId: string) => `${API_BASE_URL}/api/kb/${kbId}/documents`,
  }
};

// File upload configuration
export const SUPPORTED_FILE_TYPES: string[] = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/csv',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
];

// File type extensions
export const FILE_EXTENSIONS = {
  PDF: '.pdf',
  DOCX: '.docx',
  TXT: '.txt',
  CSV: '.csv',
  XLSX: '.xlsx',
  XLS: '.xls',
};

export const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB in bytes
