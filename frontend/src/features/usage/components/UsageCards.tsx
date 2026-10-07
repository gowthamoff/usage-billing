import { Card, Col, Progress, Row, Space, Statistic, Typography } from 'antd'
import { ThresholdTag } from '../../../components/ThresholdTag'
import { clampPercent, formatCount, formatInr, formatPercent, formatRate } from '../../../lib/money'
import { pluralUnit } from '../../../lib/units'
import type { MeterUsage, UsageState } from '../../../types/api'

const STROKE_BY_STATE: Record<UsageState, string> = {
  within_allowance: '#52c41a',
  approaching_limit: '#fa8c16',
  in_overage: '#ff4d4f',
}

interface StatProps {
  title: string
  value: number
  unit: string
  highlight?: boolean
}

function Stat({ title, value, unit, highlight = false }: StatProps) {
  return (
    <Statistic
      title={title}
      value={value}
      formatter={(raw) => formatCount(Number(raw))}
      suffix={pluralUnit(unit, value)}
      valueStyle={highlight ? { color: '#ff4d4f' } : undefined}
    />
  )
}

interface UsageCardsProps {
  meters: MeterUsage[]
  selectedMeter: string | null
  onSelectMeter: (meter: string) => void
}

export function UsageCards({ meters, selectedMeter, onSelectMeter }: UsageCardsProps) {
  return (
    <Row gutter={[16, 16]}>
      {meters.map((meter) => {
        const selected = meter.meter === selectedMeter
        return (
          <Col xs={24} md={12} xl={8} key={meter.meter}>
            <Card
              hoverable
              title={meter.display_name}
              extra={<ThresholdTag state={meter.state} />}
              onClick={() => onSelectMeter(meter.meter)}
              style={selected ? { borderColor: '#1677ff' } : undefined}
            >
              <Row gutter={[16, 16]}>
                <Col span={12}>
                  <Stat title="Used" value={meter.used} unit={meter.unit} />
                </Col>
                <Col span={12}>
                  <Stat title="Allowance" value={meter.allowance} unit={meter.unit} />
                </Col>
                <Col span={12}>
                  <Stat title="Remaining" value={meter.remaining} unit={meter.unit} />
                </Col>
                <Col span={12}>
                  <Stat title="Overage" value={meter.overage_units} unit={meter.unit} highlight={meter.overage_units > 0} />
                </Col>
              </Row>
              {/* Bar is clamped at 100 but the label shows the real percent so overage (>100%) stays visible. */}
              <Progress
                percent={clampPercent(meter.percent)}
                format={() => formatPercent(meter.percent)}
                strokeColor={STROKE_BY_STATE[meter.state]}
                status="normal"
                style={{ marginTop: 16 }}
              />
              <Space direction="vertical" size={0}>
                <Typography.Text type="secondary">Overage rate {formatRate(meter.rate_minor, meter.unit)}</Typography.Text>
                <Typography.Text strong>Overage cost this period: {formatInr(meter.cost_minor)}</Typography.Text>
              </Space>
            </Card>
          </Col>
        )
      })}
    </Row>
  )
}
