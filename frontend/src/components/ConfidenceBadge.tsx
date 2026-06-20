interface ConfidenceBadgeProps {
  score: number
}

export default function ConfidenceBadge({ score }: ConfidenceBadgeProps) {
  // Colour-coded confidence chip — implemented in Story 2.6
  const colour = score >= 0.8 ? 'bg-green-100 text-green-800' : score >= 0.5 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colour}`}>
      {(score * 100).toFixed(0)}%
    </span>
  )
}
