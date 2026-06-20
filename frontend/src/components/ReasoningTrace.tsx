interface ReasoningTraceProps {
  trace: string
}

export default function ReasoningTrace({ trace }: ReasoningTraceProps) {
  // FR-18/31: Renders agent reasoning for a transaction — implemented in Story 2.5
  return (
    <pre className="text-sm text-gray-700 whitespace-pre-wrap">{trace}</pre>
  )
}
