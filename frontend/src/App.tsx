import { useState } from 'react'
import { Typography } from 'antd'
import { Tabs } from 'antd'
import ChatPage from './pages/ChatPage'
import DocumentsPage from './pages/DocumentsPage'

const { Title } = Typography

const tabItems = [
  { key: 'documents', label: '文档管理', children: <DocumentsPage /> },
  { key: 'chat', label: '智能问答', children: <ChatPage /> },
]

function App() {
  const [activeKey, setActiveKey] = useState('documents')

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: 24 }}>
      <Title level={3}>本地知识库</Title>
      <Tabs activeKey={activeKey} onChange={setActiveKey} items={tabItems} />
    </div>
  )
}

export default App
