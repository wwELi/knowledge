import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { StyleProvider } from '@ant-design/cssinjs'
import { XProvider } from '@ant-design/x'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <StyleProvider layer>
      <XProvider>
        <ConfigProvider locale={zhCN}>
          <App />
        </ConfigProvider>
      </XProvider>
    </StyleProvider>
  </StrictMode>,
)
