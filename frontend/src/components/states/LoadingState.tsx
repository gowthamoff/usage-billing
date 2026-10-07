import { Card, Skeleton } from 'antd'

interface LoadingStateProps {
  rows?: number
  title?: string
}

export function LoadingState({ rows = 4, title }: LoadingStateProps) {
  return (
    <Card title={title}>
      <Skeleton active paragraph={{ rows }} />
    </Card>
  )
}
