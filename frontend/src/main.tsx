import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { StyleProvider } from '@ant-design/cssinjs'
import { XProvider } from '@ant-design/x'
import { App as AntdApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <StyleProvider layer>
      <XProvider>
        <ConfigProvider locale={zhCN}>
          {/* antd App 提供 App.useApp() 上下文（message/notification 等） */}
          <AntdApp>
            <App />
          </AntdApp>
        </ConfigProvider>
      </XProvider>
    </StyleProvider>
  </StrictMode>,
)
