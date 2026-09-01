import { useCallback, useEffect, useState } from 'react'
import { DeleteOutlined, FilePdfOutlined } from '@ant-design/icons'
import { App, Badge, Button, Empty, Popconfirm, Table, Tooltip, Upload } from 'antd'
import type { BadgeProps, TableProps, UploadProps } from 'antd'
import { deleteDocument, listDocuments, uploadDocument } from '../api/client'
import type { DocMeta } from '../api/client'

const STATUS_META: Record<string, { status: BadgeProps['status']; text: string }> = {
  processing: { status: 'processing', text: '解析中' },
  ready: { status: 'success', text: '已就绪' },
  failed: { status: 'error', text: '解析失败' },
}

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

/** 状态徽章：failed 且带 error 时悬停 Tooltip 显示失败原因 */
function StatusCell({ record }: { record: DocMeta }) {
  const meta = STATUS_META[record.status] ?? { status: 'default', text: record.status }
  const badge = <Badge status={meta.status} text={meta.text} />
  if (record.status === 'failed' && record.error !== null && record.error !== '') {
    return <Tooltip title={record.error}>{badge}</Tooltip>
  }
  return badge
}

function DocumentsPage() {
  const { message } = App.useApp()
  const [docs, setDocs] = useState<DocMeta[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true)
      try {
        setDocs(await listDocuments())
      } catch (err) {
        if (!silent) message.error(err instanceof Error && err.message !== '' ? err.message : '获取文档列表失败')
      } finally {
        if (!silent) setLoading(false)
      }
    },
    [message],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  // 有解析中的文档时每 3s 轮询刷新，全部完成/失败后自动停止；卸载清理定时器
  const hasProcessing = docs.some(doc => doc.status === 'processing')
  useEffect(() => {
    if (!hasProcessing) return
    const timer = window.setInterval(() => {
      void refresh(true)
    }, 3000)
    return () => window.clearInterval(timer)
  }, [hasProcessing, refresh])

  const handleDelete = async (id: string) => {
    try {
      await deleteDocument(id)
      message.success('文档已删除')
    } catch (err) {
      message.error(err instanceof Error && err.message !== '' ? err.message : '删除失败')
    }
    void refresh()
  }

  // 手动接管上传：fetch + FormData 发送，用 onProgress/onSuccess/onError 驱动进度与反馈
  const customRequest: UploadProps['customRequest'] = options => {
    const { file, onProgress, onSuccess, onError } = options
    onProgress?.({ percent: 10 })
    uploadDocument(file as File)
      .then(doc => {
        onProgress?.({ percent: 100 })
        onSuccess?.(doc)
        message.success(`「${doc.filename}」上传成功，正在后台解析`)
        void refresh()
      })
      .catch((err: unknown) => {
        onError?.(new Error(err instanceof Error && err.message !== '' ? err.message : '上传失败'))
        message.error(err instanceof Error && err.message !== '' ? err.message : '上传失败')
      })
  }

  const columns: TableProps<DocMeta>['columns'] = [
    { title: '文件名', dataIndex: 'filename', ellipsis: true },
    { title: '状态', dataIndex: 'status', width: 120, render: (_, record) => <StatusCell record={record} /> },
    { title: '块数', dataIndex: 'chunk_count', width: 90, align: 'right' },
    { title: '上传时间', dataIndex: 'created_at', width: 180, render: formatTime },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Popconfirm
          title="删除文档"
          description={`确定删除「${record.filename}」吗？`}
          okText="删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
          onConfirm={() => void handleDelete(record.id)}
        >
          <Button danger type="link" size="small" icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <Upload.Dragger accept=".pdf" multiple customRequest={customRequest}>
        <p className="ant-upload-drag-icon">
          <FilePdfOutlined />
        </p>
        <p className="ant-upload-text">拖拽或点击上传 PDF 文档</p>
        <p className="ant-upload-hint">支持单个或批量上传，仅限 .pdf 文件，上传后自动解析入库</p>
      </Upload.Dragger>
      <Table<DocMeta>
        rowKey="id"
        columns={columns}
        dataSource={docs}
        loading={loading}
        pagination={false}
        locale={{
          emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="拖拽或点击上传 PDF 文档" />,
        }}
      />
    </div>
  )
}

export default DocumentsPage
