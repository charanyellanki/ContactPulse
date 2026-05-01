interface Props {
  values: number[];
  width?: number;
  height?: number;
  invert?: boolean;
}

/** Inline SVG sparkline for the eval-runs trend column. Lightweight enough
 *  to avoid pulling in a charting library for the initial scaffold. */
export function Sparkline({ values, width = 80, height = 24, invert = false }: Props) {
  if (values.length === 0) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const points = values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * width;
      const norm = (v - min) / range;
      const y = invert ? norm * height : (1 - norm) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const last = values[values.length - 1];
  const first = values[0];
  const trendingUp = last >= first;
  const stroke = trendingUp === !invert ? "hsl(var(--success))" : "hsl(var(--destructive))";

  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden>
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
