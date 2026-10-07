import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import { UsagePage } from '../features/usage/routes/UsagePage'
import { InvoicesPage } from '../features/invoices/routes/InvoicesPage'
import { InvoiceDetailPage } from '../features/invoices/routes/InvoiceDetailPage'
import { RootRedirect } from './RootRedirect'
import { RouteError } from './RouteError'
import { NotFoundPage } from './NotFoundPage'

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { path: '/', element: <RootRedirect /> },
      {
        path: '/customers/:id',
        errorElement: <RouteError />,
        children: [
          { index: true, element: <Navigate to="usage" replace /> },
          { path: 'usage', element: <UsagePage /> },
          { path: 'invoices', element: <InvoicesPage /> },
          { path: 'invoices/:invoiceId', element: <InvoiceDetailPage /> },
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
