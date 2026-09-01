import { useCallback, useRef, useState } from 'react'
import { BASE_URL } from '../api/client'

/** 与后端 SSE `event: citations` 帧的 data 数组元素字段一一对应 */
export interface Citation {
  index: number
  filename: string
  page: number
  score: number
  snippet: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
}

export interface UseRagChatResult {
  messages: ChatMessage[]
  streaming: boolean
  error: string | null
  /** 追加一条 user 消息并向 ${BASE_URL}/api/chat 发起 SSE 流式请求 */
  send: (question: string, signal?: AbortSignal) => Promise<void>
  /** 中止当前生成（停止按钮），AbortError 不计入 error */
  stop: () => void
  clearError: () => void
}

function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === 'AbortError'
}

function asObject(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null
}

function parseJson(payload: string): unknown {
  try {
    return JSON.parse(payload)
  } catch {
    return null
  }
}

/** 解析 delta 帧 `data: {"choices":[{"delta":{"content":"..."}}]}`，非 delta 帧返回 null */
function extractDeltaContent(payload: string): string | null {
  const parsed = asObject(parseJson(payload))
  if (!parsed || !Array.isArray(parsed.choices) || parsed.choices.length === 0) return null
  const choice = asObject(parsed.choices[0])
  const delta = choice ? asObject(choice.delta) : null
  const content = delta ? delta.content : undefined
  return typeof content === 'string' ? content : null
}

function extractErrorMessage(payload: string): string {
  if (payload.trim() === '') return '上游服务异常'
  const parsed = asObject(parseJson(payload))
  if (parsed) {
    for (const key of ['message', 'detail', 'error']) {
      const value = parsed[key]
      if (typeof value === 'string' && value.trim() !== '') return value
    }
    return '上游服务异常'
  }
  return payload
}

function parseCitations(payload: string): Citation[] | null {
  const parsed = parseJson(payload)
  if (!Array.isArray(parsed)) return null
  const citations: Citation[] = []
  parsed.forEach((item, i) => {
    const obj = asObject(item)
    if (!obj) return
    citations.push({
      index: typeof obj.index === 'number' ? obj.index : i + 1,
      filename: typeof obj.filename === 'string' ? obj.filename : '',
      page: typeof obj.page === 'number' ? obj.page : 0,
      score: typeof obj.score === 'number' ? obj.score : 0,
      snippet: typeof obj.snippet === 'string' ? obj.snippet : '',
    })
  })
  return citations
}

/**
 * fetch + ReadableStream 按行缓冲解析 SSE（TextDecoder stream:true）：
 * 识别 `event:` / `data:` 帧，空行（或流结束）时派发一帧。
 */
async function consumeSseStream(
  body: ReadableStream<Uint8Array>,
  onFrame: (event: string, data: string) => void,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let eventName = ''
  let dataLines: string[] = []

  const dispatchFrame = () => {
    if (dataLines.length === 0) {
      eventName = ''
      return
    }
    onFrame(eventName, dataLines.join('\n'))
    eventName = ''
    dataLines = []
  }

  const handleLine = (raw: string) => {
    const line = raw.endsWith('\r') ? raw.slice(0, -1) : raw
    if (line === '') {
      dispatchFrame()
      return
    }
    if (line.startsWith(':')) return // SSE 注释/心跳
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim()
      return
    }
    if (line.startsWith('data:')) {
      const value = line.slice('data:'.length)
      dataLines.push(value.startsWith(' ') ? value.slice(1) : value)
    }
    // 其余字段（id:/retry:）忽略
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let newlineIndex = buffer.indexOf('\n')
      while (newlineIndex !== -1) {
        handleLine(buffer.slice(0, newlineIndex))
        buffer = buffer.slice(newlineIndex + 1)
        newlineIndex = buffer.indexOf('\n')
      }
    }
    buffer += decoder.decode()
    if (buffer !== '') handleLine(buffer)
    dispatchFrame()
  } finally {
    reader.releaseLock()
  }
}

export function useRagChat(): UseRagChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 回调内读取最新值用，避免闭包过期
  const messagesRef = useRef<ChatMessage[]>([])
  const streamingRef = useRef(false)
  const controllerRef = useRef<AbortController | null>(null)

  const updateMessages = useCallback((updater: (prev: ChatMessage[]) => ChatMessage[]) => {
    setMessages(prev => {
      const next = updater(prev)
      messagesRef.current = next
      return next
    })
  }, [])

  const updateLastAssistant = useCallback(
    (updater: (msg: ChatMessage) => ChatMessage) => {
      updateMessages(prev => {
        const last = prev[prev.length - 1]
        if (!last || last.role !== 'assistant') return prev
        return [...prev.slice(0, -1), updater(last)]
      })
    },
    [updateMessages],
  )

  const clearError = useCallback(() => setError(null), [])

  const stop = useCallback(() => {
    controllerRef.current?.abort()
  }, [])

  const send = useCallback(
    async (question: string, signal?: AbortSignal) => {
      const trimmed = question.trim()
      if (trimmed === '' || streamingRef.current) return
      streamingRef.current = true
      setStreaming(true)
      setError(null)

      const controller = new AbortController()
      controllerRef.current = controller
      // 外部 signal 一并接入（任一 abort 都生效）
      const onExternalAbort = () => controller.abort()
      signal?.addEventListener('abort', onExternalAbort, { once: true })

      const userMessage: ChatMessage = { role: 'user', content: trimmed }
      // 同会话多轮：把全部历史 + 本轮问题传给后端；对话历史仅存组件 state
      const history = [...messagesRef.current, userMessage]
      updateMessages(prev => [...prev, userMessage, { role: 'assistant', content: '' }])

      try {
        const response = await fetch(`${BASE_URL}/api/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: history.map(({ role, content }) => ({ role, content })),
          }),
          signal: controller.signal,
        })
        if (!response.ok || !response.body) {
          throw new Error(`后端响应异常（HTTP ${response.status}）`)
        }
        await consumeSseStream(response.body, (event, data) => {
          if (data === '[DONE]') return
          if (event === 'citations') {
            const citations = parseCitations(data)
            if (citations) updateLastAssistant(msg => ({ ...msg, citations }))
            return
          }
          if (event === 'error') {
            setError(extractErrorMessage(data))
            return
          }
          if (event !== '') return
          const delta = extractDeltaContent(data)
          if (delta) updateLastAssistant(msg => ({ ...msg, content: msg.content + delta }))
        })
      } catch (err) {
        // 失败/中止时保留已生成的部分内容，但移除空的占位气泡
        updateMessages(prev => {
          const last = prev[prev.length - 1]
          if (last && last.role === 'assistant' && last.content === '') return prev.slice(0, -1)
          return prev
        })
        if (isAbortError(err)) {
          // 用户主动停止：不作为错误展示
        } else if (err instanceof TypeError) {
          setError('无法连接后端')
        } else {
          setError(err instanceof Error && err.message !== '' ? err.message : '无法连接后端')
        }
      } finally {
        signal?.removeEventListener('abort', onExternalAbort)
        controllerRef.current = null
        streamingRef.current = false
        setStreaming(false)
      }
    },
    [updateLastAssistant, updateMessages],
  )

  return { messages, streaming, error, send, stop, clearError }
}
