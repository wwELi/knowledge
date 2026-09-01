export const BASE_URL = 'http://localhost:8000'

/** 文档元数据，与后端 `GET /api/documents` 返回字段逐一对应（id 为 UUID 字符串） */
export interface DocMeta {
  id: string
  filename: string
  status: string
  chunk_count: number
  error: string | null
  created_at: string
}

function asObject(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null
}

/** 从错误响应/异常中提取可读信息（detail 字符串、FastAPI detail 数组、message/error 字段） */
function extractErrorMessage(payload: string, fallback: string): string {
  if (payload.trim() === '') return fallback
  const parsed = asObject(JSON.parse(payload))
  if (!parsed) return payload
  const detail = parsed.detail
  if (typeof detail === 'string' && detail.trim() !== '') return detail
  if (Array.isArray(detail)) {
    const msg = asObject(detail[0])?.msg
    if (typeof msg === 'string' && msg.trim() !== '') return msg
  }
  for (const key of ['message', 'error']) {
    const value = parsed[key]
    if (typeof value === 'string' && value.trim() !== '') return value
  }
  return fallback
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  return extractErrorMessage(await response.text().catch(() => ''), fallback)
}

/** 兼容 `{ documents: [...] }` 与直接数组两种返回形状 */
function extractDocumentArray(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload
  const documents = asObject(payload)?.documents
  return Array.isArray(documents) ? documents : []
}

/** 逐字段归一化，剔除后端可能返回的脏数据行 */
function toDocMeta(value: unknown): DocMeta | null {
  const obj = asObject(value)
  if (!obj) return null
  const id = obj.id
  if (typeof id !== 'string' || id === '') return null
  return {
    id,
    filename: typeof obj.filename === 'string' ? obj.filename : '',
    status: typeof obj.status === 'string' ? obj.status : 'processing',
    chunk_count: typeof obj.chunk_count === 'number' ? obj.chunk_count : 0,
    error: typeof obj.error === 'string' ? obj.error : null,
    created_at: typeof obj.created_at === 'string' ? obj.created_at : '',
  }
}

export async function listDocuments(): Promise<DocMeta[]> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}/api/documents`)
  } catch {
    throw new Error('无法连接后端')
  }
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `获取文档列表失败（HTTP ${response.status}）`))
  }
  const list = extractDocumentArray(await response.json().catch(() => null))
  return list.map(toDocMeta).filter((doc): doc is DocMeta => doc !== null)
}

export async function uploadDocument(file: File): Promise<DocMeta> {
  const formData = new FormData()
  formData.append('file', file)
  let response: Response
  try {
    response = await fetch(`${BASE_URL}/api/documents`, { method: 'POST', body: formData })
  } catch {
    throw new Error('无法连接后端')
  }
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `上传失败（HTTP ${response.status}）`))
  }
  const doc = toDocMeta(await response.json().catch(() => null))
  if (!doc) throw new Error('上传成功但后端返回格式异常')
  return doc
}

export async function deleteDocument(id: string): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}/api/documents/${id}`, { method: 'DELETE' })
  } catch {
    throw new Error('无法连接后端')
  }
  if (!response.ok && response.status !== 404) {
    throw new Error(await readErrorMessage(response, `删除失败（HTTP ${response.status}）`))
  }
}
