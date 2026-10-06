// Authored illustrative geometry. No team model, telemetry or race positioning.
export type Vec3 = [number, number, number];
export interface Triangle {
  points: [Vec3, Vec3, Vec3];
  normal: Vec3;
  color: Vec3;
}
export const DEFAULT_YAW = -0.55;
export const PITCH = 0.36;
export const VIEW_WIDTH = 3.05;
const body: Vec3 = [0.68, 0.69, 0.72];
const accent: Vec3 = [0.93, 0.4, 0.29];
const dark: Vec3 = [0.075, 0.077, 0.085];
const metal: Vec3 = [0.34, 0.35, 0.38];
const light: Vec3 = [0.94, 0.93, 0.91];

export function carGeometry(): Triangle[] {
  const triangles: Triangle[] = [];
  function triangle(a: Vec3, b: Vec3, c: Vec3, color: Vec3) {
    const u = b.map((value, index) => value - a[index]);
    const v = c.map((value, index) => value - a[index]);
    const cross = [
      u[1] * v[2] - u[2] * v[1],
      u[2] * v[0] - u[0] * v[2],
      u[0] * v[1] - u[1] * v[0],
    ];
    const length = Math.hypot(...cross);
    if (length < 0.000001) return;
    triangles.push({
      points: [a, b, c],
      normal: cross.map((value) => value / length) as Vec3,
      color,
    });
  }
  function hull(
    x1: number,
    x2: number,
    y1: number,
    y2: number,
    w1: number,
    w2: number,
    floor: number,
    color: Vec3,
  ) {
    const points: Vec3[] = [
      [x1, floor, -w1],
      [x2, floor, -w2],
      [x2, y2, -w2],
      [x1, y1, -w1],
      [x1, floor, w1],
      [x2, floor, w2],
      [x2, y2, w2],
      [x1, y1, w1],
    ];
    for (const face of [
      [0, 3, 2, 1],
      [4, 5, 6, 7],
      [0, 4, 7, 3],
      [1, 2, 6, 5],
      [0, 1, 5, 4],
      [3, 7, 6, 2],
    ]) {
      triangle(points[face[0]], points[face[1]], points[face[2]], color);
      triangle(points[face[0]], points[face[2]], points[face[3]], color);
    }
  }
  function box(
    x: number,
    y: number,
    z: number,
    length: number,
    height: number,
    width: number,
    color: Vec3,
  ) {
    const start = triangles.length;
    hull(
      x - length / 2,
      x + length / 2,
      y + height / 2,
      y + height / 2,
      width / 2,
      width / 2,
      y - height / 2,
      color,
    );
    for (const point of new Set(
      triangles.slice(start).flatMap((row) => row.points),
    ))
      point[2] += z;
  }
  function cylinder(
    x: number,
    y: number,
    z: number,
    radius: number,
    width: number,
    color: Vec3,
    segments = 18,
  ) {
    for (let index = 0; index < segments; index++) {
      const a = (index * Math.PI * 2) / segments,
        b = ((index + 1) * Math.PI * 2) / segments;
      const p: Vec3 = [
        x + radius * Math.cos(a),
        y + radius * Math.sin(a),
        z - width / 2,
      ];
      const q: Vec3 = [
        x + radius * Math.cos(b),
        y + radius * Math.sin(b),
        z - width / 2,
      ];
      const r: Vec3 = [q[0], q[1], z + width / 2],
        s: Vec3 = [p[0], p[1], z + width / 2];
      triangle(p, q, r, color);
      triangle(p, r, s, color);
      triangle([x, y, z - width / 2], q, p, color);
      triangle([x, y, z + width / 2], s, r, color);
    }
  }
  // Floor, sculpted nose, cockpit, sidepods and engine cover.
  hull(-1.9, 1.9, 0.2, 0.2, 0.37, 0.63, 0.12, dark);
  hull(-2.2, -0.4, 0.32, 0.63, 0.09, 0.25, 0.22, body);
  hull(-0.5, 0.95, 0.62, 0.7, 0.3, 0.3, 0.22, body);
  hull(0.5, 1.7, 1.03, 0.47, 0.16, 0.24, 0.22, body);
  for (const side of [-1, 1]) {
    box(0.55, 0.32, side * 0.57, 1.75, 0.28, 0.45, body);
    box(0.45, 0.48, side * 0.57, 1.3, 0.035, 0.43, accent);
    box(-0.31, 0.43, side * 0.57, 0.055, 0.18, 0.33, dark);
  }
  box(0.0, 0.685, 0, 0.67, 0.1, 0.4, dark);
  box(0.44, 0.83, 0, 0.18, 0.22, 0.22, dark);
  // Halo / rollover structure is an illustrative simplified silhouette.
  box(0.04, 0.91, -0.23, 0.67, 0.035, 0.035, metal);
  box(0.04, 0.91, 0.23, 0.67, 0.035, 0.035, metal);
  box(-0.28, 0.91, 0, 0.035, 0.035, 0.49, metal);
  box(-0.26, 0.8, 0, 0.045, 0.22, 0.05, metal);
  box(0.34, 0.78, -0.23, 0.045, 0.22, 0.045, metal);
  box(0.34, 0.78, 0.23, 0.045, 0.22, 0.045, metal);
  // Wing planes and endplates.
  box(-2.03, 0.24, 0, 0.42, 0.06, 2.15, dark);
  box(-1.86, 0.31, 0, 0.13, 0.04, 2.08, body);
  box(1.93, 1.0, 0, 0.35, 0.09, 1.84, dark);
  box(1.88, 1.07, 0, 0.24, 0.025, 1.77, accent);
  for (const side of [-1, 1]) {
    box(-2.03, 0.31, side * 1.08, 0.44, 0.19, 0.035, accent);
    box(1.91, 0.86, side * 0.93, 0.38, 0.37, 0.035, body);
    box(1.9, 0.64, side * 0.29, 0.04, 0.58, 0.04, metal);
  }
  // Four open wheels, hubs, and suspension. These are not measured dimensions.
  for (const x of [-1.42, 1.38])
    for (const side of [-1, 1]) {
      cylinder(x, 0.43, side * 0.94, 0.43, 0.32, dark);
      cylinder(x, 0.43, side * 1.105, 0.24, 0.012, metal);
      cylinder(x, 0.43, side * 1.116, 0.085, 0.013, light);
      box(x, 0.36, side * 0.55, 0.085, 0.065, 0.76, metal);
    }
  return triangles;
}

export function rotate(point: Vec3, yaw: number): Vec3 {
  const c = Math.cos(yaw),
    s = Math.sin(yaw);
  return [c * point[0] + s * point[2], point[1], -s * point[0] + c * point[2]];
}
export function viewWidth(aspect: number): number {
  return VIEW_WIDTH * Math.max(1, aspect / (720 / 320));
}
export function project(point: Vec3, yaw: number, aspect: number): Vec3 {
  const [x, y, z] = rotate(point, yaw);
  const centered = y - 0.47;
  const halfWidth = viewWidth(aspect);
  return [
    x / halfWidth,
    ((Math.cos(PITCH) * centered - Math.sin(PITCH) * z) * aspect) / halfWidth,
    -(Math.sin(PITCH) * centered + Math.cos(PITCH) * z) / 8,
  ];
}
export function renderSize(width: number, height: number, density: number) {
  const w = Number.isFinite(width) ? Math.max(1, width) : 1;
  const h = Number.isFinite(height) ? Math.max(1, height) : 1;
  const ratio = Number.isFinite(density)
    ? Math.max(1, Math.min(density, 1.5))
    : 1;
  const scale = Math.min(
    ratio,
    1600 / w,
    1000 / h,
    Math.sqrt(600000 / (w * h)),
  );
  return {
    width: Math.max(1, Math.floor(w * scale)),
    height: Math.max(1, Math.floor(h * scale)),
  };
}

// A deterministic non-WebGL rendering of the same authored model.
export function carSvg(): string {
  const width = 720,
    height = 320;
  const rows = carGeometry()
    .map((row) => {
      const points = row.points.map((point) =>
        project(point, DEFAULT_YAW, width / height),
      );
      const normal = rotate(row.normal, DEFAULT_YAW);
      const brightness =
        0.48 +
        0.52 *
          Math.max(0, normal[0] * -0.36 + normal[1] * 0.8 + normal[2] * 0.48);
      const color = row.color.map((channel) =>
        Math.round(Math.min(1, channel * brightness) * 255),
      );
      return {
        depth: points.reduce((sum, point) => sum + point[2], 0) / 3,
        polygon: `<polygon points="${points.map(([x, y]) => `${(((x + 1) * width) / 2).toFixed(1)},${(((1 - y) * height) / 2).toFixed(1)}`).join(" ")}" fill="rgb(${color.join(",")})"/>`,
      };
    })
    .sort((a, b) => b.depth - a.depth);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}"><title>Illustrative open-wheel car</title><desc>Authored geometry, not a team car or race replay.</desc>${rows.map((row) => row.polygon).join("")}</svg>\n`;
}
