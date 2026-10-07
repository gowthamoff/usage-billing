import { Alert, Button } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

interface ErrorStateProps {
  message: string
  title?: string
  onRetry: () => void
  retrying?: boolean
}

export function ErrorState({ message, title = 'Could not load data', onRetry, retrying = false }: ErrorStateProps) {
  return (
    <Alert
      type="error"
      showIcon
      message={title}
      description={message}
      action={
        <Button size="small" icon={<ReloadOutlined />} onClick={onRetry} loading={retrying}>
          Retry
        </Button>
      }
    />
  )
}
