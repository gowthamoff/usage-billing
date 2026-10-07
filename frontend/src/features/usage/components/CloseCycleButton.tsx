import { App, Button, Popconfirm, Typography } from 'antd'
import { FileDoneOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useCloseCycle } from '../api/close-cycle'
import { errorMessage } from '../../../lib/api-client'
import { formatInr } from '../../../lib/money'

/** Demo convenience: force-closes the current cycle and links to the resulting invoice. */
export function CloseCycleButton({ customerId }: { customerId: string }) {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const closeCycle = useCloseCycle(customerId)

  const onConfirm = async () => {
    try {
      const { invoice, created } = await closeCycle.mutateAsync({ force: true })
      message.success({
        duration: 8,
        content: (
          <span>
            {created ? 'Invoice issued: ' : 'Cycle was already closed. Existing invoice: '}
            <Typography.Link onClick={() => navigate(`/customers/${customerId}/invoices/${invoice.id}`)}>
              {invoice.id}
            </Typography.Link>
            {` · total ${formatInr(invoice.total_minor)}`}
          </span>
        ),
      })
    } catch (error) {
      message.error(errorMessage(error))
    }
  }

  return (
    <Popconfirm
      title="Close the current cycle now?"
      description="Demo only: issues an invoice for the current period as of this moment."
      okText="Close cycle"
      onConfirm={onConfirm}
    >
      <Button type="primary" icon={<FileDoneOutlined />} loading={closeCycle.isPending}>
        Close cycle
      </Button>
    </Popconfirm>
  )
}
