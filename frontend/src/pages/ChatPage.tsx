import { useState } from 'react'
import type { ReactNode } from 'react'
import { RobotOutlined, UserOutlined } from '@ant-design/icons'
import { Bubble, Sender } from '@ant-design/x'
import type { BubbleItemType, BubbleListProps } from '@ant-design/x'
import { Alert, Avatar, Popover, Typography, theme } from 'antd'
import { useRagChat } from '../hooks/useRagChat'
import type { Citation } from '../hooks/useRagChat'

/** 回答文本中的 [n] 角标：有对应引用时用 Popover 展示出处，没有则原样渲染 */
function CitationBadge({ index, citation }: { index: number; citation: Citation | undefined }) {
  const { token } = theme.useToken()
  if (!citation) {
    return <sup style={{ color: token.colorTextQuaternary }}>[{index}]</sup>
  }
  return (
    <Popover
      trigger={['hover', 'click']}
      title={citation.filename}
      content={
        <div style={{ maxWidth: 320 }}>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 4 }}>
            第 {citation.page} 页 · 相似度 {citation.score.toFixed(3)}
          </Typography.Paragraph>
          <Typography.Paragraph style={{ marginBottom: 0 }}>{citation.snippet}</Typography.Paragraph>
        </div>
      }
    >
      <sup style={{ color: token.colorPrimary, cursor: 'pointer', userSelect: 'none' }}>[{index}]</sup>
    </Popover>
  )
}

/** 纯文本 + [n] 上标角标渲染（不做 markdown） */
function renderAssistantContent(content: string, citations: Citation[]): ReactNode {
  return content.split(/(\[\d+\])/g).map((part, i) => {
    const match = /^\[(\d+)\]$/.exec(part)
    if (!match) return <span key={i}>{part}</span>
    const citedIndex = Number(match[1])
    return (
      <CitationBadge
        key={i}
        index={citedIndex}
        citation={citations.find(c => c.index === citedIndex)}
      />
    )
  })
}

function ChatPage() {
  const { messages, streaming, error, send, stop, clearError } = useRagChat()
  const [input, setInput] = useState('')
  const { token } = theme.useToken()

  const handleSend = (question: string) => {
    const trimmed = question.trim()
    if (trimmed === '' || streaming) return
    setInput('')
    void send(trimmed)
  }

  const roles: BubbleListProps['role'] = {
    ai: {
      placement: 'start',
      avatar: (
        <Avatar icon={<RobotOutlined />} style={{ backgroundColor: token.colorPrimary }} />
      ),
      variant: 'outlined',
      styles: { content: { whiteSpace: 'pre-wrap' } },
    },
    user: {
      placement: 'end',
      avatar: <Avatar icon={<UserOutlined />} />,
      variant: 'filled',
      styles: { content: { whiteSpace: 'pre-wrap' } },
    },
  }

  const items: BubbleItemType[] = messages.map((msg, i) => {
    if (msg.role === 'user') {
      return { key: `msg-${i}`, role: 'user', content: msg.content }
    }
    const isStreamingNow = streaming && i === messages.length - 1
    return {
      key: `msg-${i}`,
      role: 'ai',
      content: msg.content,
      // 内容为空时展示 loading 圆点，随后随 SSE delta 流式逐字追加
      loading: isStreamingNow && msg.content === '',
      streaming: isStreamingNow,
      contentRender: (content: string) => renderAssistantContent(content, msg.citations ?? []),
    }
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, height: 'calc(100vh - 176px)' }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        {messages.length === 0 && error === null ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Typography.Paragraph type="secondary">
              本地知识库问答助手已就绪，输入问题开始提问。
            </Typography.Paragraph>
          </div>
        ) : (
          <Bubble.List items={items} role={roles} style={{ height: '100%', overflowY: 'auto' }} />
        )}
      </div>
      {error !== null && (
        <Alert type="error" showIcon message={error} closable onClose={clearError} />
      )}
      <Sender
        value={input}
        onChange={setInput}
        placeholder="输入问题，Enter 发送 / Shift+Enter 换行"
        loading={streaming}
        onSubmit={handleSend}
        onCancel={stop}
      />
    </div>
  )
}

export default ChatPage
