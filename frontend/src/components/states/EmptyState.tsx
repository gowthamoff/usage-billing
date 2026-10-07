import type { ReactNode } from 'react'
import { Card, Empty } from 'antd'

interface EmptyStateProps {
  description: ReactNode
  title?: string
  children?: ReactNode
}

export function EmptyState({ description, title, children }: EmptyStateProps) {
  return (
    <Card title={title}>
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description}>
        {children}
      </Empty>
    </Card>
  )
}
