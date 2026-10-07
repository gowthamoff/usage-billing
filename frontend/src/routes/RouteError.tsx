import { Alert, Button } from 'antd'
import { isRouteErrorResponse, useRouteError } from 'react-router-dom'
import { errorMessage } from '../lib/api-client'

export function RouteError() {
  const error = useRouteError()
  const description = isRouteErrorResponse(error) ? `${error.status} ${error.statusText}` : errorMessage(error)

  return (
    <Alert
      type="error"
      showIcon
      message="Something went wrong"
      description={description}
      action={
        <Button size="small" onClick={() => window.location.reload()}>
          Reload
        </Button>
      }
    />
  )
}
