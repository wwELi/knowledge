export const BASE_URL = 'http://localhost:8000'

/** 文档元数据，与后端 T6 `GET /api/documents` 返回字段逐一对应 */
export interface DocMeta {
  id: number
  filename: string
  status: string
  chunk_count: number
  error: string | null
  created_at: string
}

// TODO(T8): GET ${BASE_URL}/api/documents，解析 JSON 为 DocMeta[]
export async function listDocuments(): Promise<DocMeta[]> {
  throw new Error('not implemented')
}

// TODO(T8): POST FormData(file) 到 ${BASE_URL}/api/documents/upload
export async function uploadDocument(_file: File): Promise<DocMeta> {
  throw new Error('not implemented')
}

// TODO(T8): DELETE ${BASE_URL}/api/documents/{id}
export async function deleteDocument(_id: number): Promise<void> {
  throw new Error('not implemented')
}
