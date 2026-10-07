import { useEffect, useMemo } from 'react'
import { Layout, Menu, Select, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { Link, Outlet, useLocation, useMatch, useNavigate } from 'react-router-dom'
import { useCustomers } from '../../features/customers/api/get-customers'
import { useUiStore } from '../../stores/ui-store'

type Section = 'usage' | 'invoices'

export function AppShell() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const match = useMatch('/customers/:id/*')
  const routeCustomerId = match?.params.id ?? null
  const section: Section = pathname.includes('/invoices') ? 'invoices' : 'usage'

  const customers = useCustomers()
  const selectedCustomerId = useUiStore((state) => state.selectedCustomerId)
  const setSelectedCustomerId = useUiStore((state) => state.setSelectedCustomerId)

  useEffect(() => {
    if (routeCustomerId) setSelectedCustomerId(routeCustomerId)
  }, [routeCustomerId, setSelectedCustomerId])

  const activeCustomerId = routeCustomerId ?? selectedCustomerId

  const options = useMemo(
    () => (customers.data ?? []).map((customer) => ({ value: customer.id, label: `${customer.name} (${customer.id})` })),
    [customers.data],
  )

  const menuItems: MenuProps['items'] = [
    {
      key: 'usage',
      disabled: !activeCustomerId,
      label: activeCustomerId ? <Link to={`/customers/${activeCustomerId}/usage`}>Usage</Link> : 'Usage',
    },
    {
      key: 'invoices',
      disabled: !activeCustomerId,
      label: activeCustomerId ? <Link to={`/customers/${activeCustomerId}/invoices`}>Invoices</Link> : 'Invoices',
    },
  ]

  const onCustomerChange = (id: string) => {
    setSelectedCustomerId(id)
    navigate(`/customers/${id}/${section}`)
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Header style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        <Typography.Title level={4} style={{ color: '#fff', margin: 0, whiteSpace: 'nowrap' }}>
          Usage &amp; Billing
        </Typography.Title>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[section]}
          items={menuItems}
          style={{ flex: 1, minWidth: 0 }}
        />
        <Select<string>
          showSearch
          optionFilterProp="label"
          placeholder={customers.isError ? 'Customers unavailable' : 'Select customer'}
          loading={customers.isPending}
          status={customers.isError ? 'error' : undefined}
          value={activeCustomerId ?? undefined}
          options={options}
          onChange={onCustomerChange}
          style={{ width: 280 }}
        />
      </Layout.Header>
      <Layout.Content className="app-content">
        <Outlet />
      </Layout.Content>
    </Layout>
  )
}
