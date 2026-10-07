import { Button, Result } from 'antd'
import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <Result
      status="404"
      title="Page not found"
      subTitle="The page you are looking for does not exist."
      extra={
        <Link to="/">
          <Button type="primary">Go to usage</Button>
        </Link>
      }
    />
  )
}
