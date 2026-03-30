import './EmptyState.css'

interface EmptyStateProps {
  icon?: string
  title: string
  description: string
  steps?: { label: string; detail: string }[]
  action?: { label: string; href?: string; onClick?: () => void }
}

export function EmptyState({ icon, title, description, steps, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {icon && <span className="empty-state-icon">{icon}</span>}
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-description">{description}</p>
      {steps && steps.length > 0 && (
        <ol className="empty-state-steps">
          {steps.map((step, i) => (
            <li key={i}>
              <strong>{step.label}</strong>
              <span>{step.detail}</span>
            </li>
          ))}
        </ol>
      )}
      {action && (
        <div className="empty-state-action">
          {action.href ? (
            <a href={action.href} target="_blank" rel="noopener noreferrer">
              {action.label}
            </a>
          ) : (
            <button type="button" onClick={action.onClick}>
              {action.label}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
