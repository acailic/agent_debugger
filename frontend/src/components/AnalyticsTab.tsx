import CostSummary from './CostSummary'
import { AnalyticsPanel } from './AnalyticsPanel'
import './AnalyticsTab.css'

export function AnalyticsTab() {
  return (
    <div className="analytics-view fade-in">
      <CostSummary />
      <AnalyticsPanel />
    </div>
  )
}
