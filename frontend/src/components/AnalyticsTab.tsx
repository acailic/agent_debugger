import CostSummary from './CostSummary'
import { AnalyticsPanel } from './AnalyticsPanel'
import { AlertDashboardPanel } from './AlertDashboardPanel'
import { PortfolioAuditPanel } from './PortfolioAuditPanel'
import { useAuditPortfolio } from '../hooks/useAuditPortfolio'
import { useSessionStore } from '../stores/sessionStore'
import './AnalyticsTab.css'

export function AnalyticsTab() {
  // Fetch the cross-session audit portfolio once on mount.
  useAuditPortfolio()

  const portfolioReport = useSessionStore((state) => state.portfolioReport)
  const portfolioLoading = useSessionStore((state) => state.portfolioLoading)
  const portfolioError = useSessionStore((state) => state.portfolioError)

  return (
    <div className="analytics-view fade-in">
      <PortfolioAuditPanel
        report={portfolioReport}
        loading={portfolioLoading}
        error={portfolioError}
      />
      <CostSummary />
      <AnalyticsPanel />
      <AlertDashboardPanel agentName={null} />
    </div>
  )
}
