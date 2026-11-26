interface SparklineProps {
  values: number[]
  width?: number
  height?: number
}

// Turns values into "x,y x,y ..." for an SVG polyline. The highest value
// touches the top and zero touches the bottom, with a 2 px margin.
export function sparklinePoints(values: number[], width: number, height: number): string {
  if (values.length < 2) {
    return ''
  }
  const max = Math.max(...values, 1)
  const step = width / (values.length - 1)
  return values
    .map((value, index) => {
      const x = index * step
      const y = height - 2 - (value / max) * (height - 4)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

export function Sparkline({ values, width = 600, height = 48 }: SparklineProps) {
  const points = sparklinePoints(values, width, height)
  const last = values.at(-1)
  return (
    <div className="spark">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        width="100%"
        height={height}
        role="img"
        aria-label="Ediciones por segundo"
      >
        {points && <polyline fill="none" stroke="var(--accent)" strokeWidth="2" points={points} />}
      </svg>
      <span className="spark-value">{last === undefined ? '–' : `${last.toFixed(1)} ed/s`}</span>
    </div>
  )
}
