// Map math for the incidents map: an equirectangular projection where one
// degree is one unit. The map shows 84° N to 58° S, like the land dots.
import { LAND_LAT_MAX, LAND_LAT_MIN, LAND_ROWS, LAND_STEP } from '../data/landDots'

export const MAP_WIDTH = 360
export const MAP_HEIGHT = LAND_LAT_MAX - LAND_LAT_MIN

export interface MapPoint {
  x: number
  y: number
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

// Longitude -180..180 goes to x 0..360. Latitude 84..-58 goes to y 0..142.
// A point outside the map (for example Antarctica) stays on its edge.
export function project(lat: number, lon: number): MapPoint {
  return {
    x: clamp(lon, -180, 180) + 180,
    y: LAND_LAT_MAX - clamp(lat, LAND_LAT_MIN, LAND_LAT_MAX),
  }
}

// Expands the runs of LAND_ROWS to one [lon, lat] pair per dot.
export function landDots(rows: number[][] = LAND_ROWS, step: number = LAND_STEP): [number, number][] {
  const dots: [number, number][] = []
  for (const [lat, ...runs] of rows) {
    for (let index = 0; index + 1 < runs.length; index += 2) {
      for (let lon = runs[index]; lon <= runs[index + 1]; lon += step) {
        dots.push([lon, lat])
      }
    }
  }
  return dots
}

// One SVG path with a small circle per dot. One element draws faster than thousands.
export function dotsPath(dots: [number, number][], radius: number): string {
  const r = radius.toFixed(2)
  const d = (radius * 2).toFixed(2)
  return dots
    .map(([lon, lat]) => {
      const { x, y } = project(lat, lon)
      return `M${(x - radius).toFixed(2)} ${y.toFixed(2)}a${r} ${r} 0 1 0 ${d} 0a${r} ${r} 0 1 0 -${d} 0`
    })
    .join('')
}
