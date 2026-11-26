import { describe, expect, it } from 'vitest'
import { LAND_ROWS } from '../data/landDots'
import { dotsPath, landDots, MAP_HEIGHT, MAP_WIDTH, project } from './geo'

describe('project', () => {
  it('maps longitude to x and latitude to y, one unit per degree', () => {
    expect(project(84, -180)).toEqual({ x: 0, y: 0 })
    expect(project(0, 0)).toEqual({ x: 180, y: 84 })
    expect(project(-58, 180)).toEqual({ x: 360, y: 142 })
    // Guadalajara.
    const guadalajara = project(20.67, -103.35)
    expect(guadalajara.x).toBeCloseTo(76.65)
    expect(guadalajara.y).toBeCloseTo(63.33)
  })

  it('keeps points outside the map on its edge', () => {
    expect(project(-80, 200)).toEqual({ x: MAP_WIDTH, y: MAP_HEIGHT })
    expect(project(89, -190)).toEqual({ x: 0, y: 0 })
  })
})

describe('landDots', () => {
  it('expands each run of a row', () => {
    expect(landDots([[11, -3, 1, 7, 7]], 2)).toEqual([
      [-3, 11],
      [-1, 11],
      [1, 11],
      [7, 11],
    ])
  })

  it('has land in the generated data', () => {
    const dots = landDots()
    expect(LAND_ROWS.length).toBeGreaterThan(50)
    expect(dots.length).toBeGreaterThan(3000)
    // The dot nearest to Guadalajara (21° N, 103° W) is land. The middle of the Pacific is not.
    expect(dots).toContainEqual([-103, 21])
    expect(dots).not.toContainEqual([-151, 1])
  })
})

describe('dotsPath', () => {
  it('draws one small circle per dot', () => {
    expect(dotsPath([[0, 0]], 0.5)).toBe('M179.50 84.00a0.50 0.50 0 1 0 1.00 0a0.50 0.50 0 1 0 -1.00 0')
    expect(dotsPath([], 0.5)).toBe('')
  })
})
