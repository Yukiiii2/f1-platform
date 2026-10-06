import {
  carGeometry,
  DEFAULT_YAW,
  PITCH,
  renderSize,
  viewWidth,
} from "../_lib/car-geometry";

export interface CarRenderer {
  draw(yaw: number): boolean;
  dispose(): void;
}
export function createCarRenderer(
  canvas: HTMLCanvasElement,
  unavailable: () => void,
): CarRenderer | null {
  const gl = canvas.getContext("webgl", {
    antialias: false,
    alpha: true,
    depth: true,
    powerPreference: "low-power",
    failIfMajorPerformanceCaveat: true,
  });
  if (!gl) return null;
  const release: (() => void)[] = [];
  let disposed = false;
  let observer: ResizeObserver | undefined;
  function dispose() {
    if (disposed) return;
    disposed = true;
    observer?.disconnect();
    canvas.removeEventListener("webglcontextlost", lost);
    release.reverse().forEach((cleanup) => cleanup());
    gl!.getExtension("WEBGL_lose_context")?.loseContext();
  }
  function lost(event: Event) {
    event.preventDefault();
    unavailable();
  }
  try {
    function shader(type: number, source: string) {
      const value = gl!.createShader(type);
      if (!value) throw new Error("Renderer unavailable");
      release.push(() => gl!.deleteShader(value));
      gl!.shaderSource(value, source);
      gl!.compileShader(value);
      return value;
    }
    const vertex = shader(
      gl.VERTEX_SHADER,
      `
      attribute vec3 a_position; attribute vec3 a_normal; attribute vec3 a_color;
      uniform float u_yaw; uniform float u_aspect; uniform float u_view_width; varying vec3 v_color;
      void main() {
        float c=cos(u_yaw); float s=sin(u_yaw);
        vec3 p=vec3(c*a_position.x+s*a_position.z,a_position.y-0.47,-s*a_position.x+c*a_position.z);
        vec3 n=vec3(c*a_normal.x+s*a_normal.z,a_normal.y,-s*a_normal.x+c*a_normal.z);
        gl_Position=vec4(p.x/u_view_width,(cos(${PITCH})*p.y-sin(${PITCH})*p.z)*u_aspect/u_view_width,-(sin(${PITCH})*p.y+cos(${PITCH})*p.z)/8.0,1.0);
        v_color=a_color*(0.48+0.52*max(0.0,dot(n,vec3(-0.36,0.8,0.48))));
      }`,
    );
    const fragment = shader(
      gl.FRAGMENT_SHADER,
      `precision mediump float; varying vec3 v_color; void main() { gl_FragColor=vec4(v_color,1.0); }`,
    );
    const program = gl.createProgram();
    if (!program) throw new Error("Renderer unavailable");
    release.push(() => gl.deleteProgram(program));
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.bindAttribLocation(program, 0, "a_position");
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS))
      throw new Error("Renderer unavailable");
    gl.useProgram(program);
    const buffer = gl.createBuffer();
    if (!buffer) throw new Error("Renderer unavailable");
    release.push(() => gl.deleteBuffer(buffer));
    const vertices = carGeometry().flatMap((row) =>
      row.points.flatMap((point) => [...point, ...row.normal, ...row.color]),
    );
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);
    for (const [index, name] of [
      "a_position",
      "a_normal",
      "a_color",
    ].entries()) {
      const location = gl.getAttribLocation(program, name);
      if (location < 0) throw new Error("Renderer unavailable");
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, 3, gl.FLOAT, false, 36, index * 12);
    }
    const yaw = gl.getUniformLocation(program, "u_yaw"),
      aspect = gl.getUniformLocation(program, "u_aspect"),
      halfWidth = gl.getUniformLocation(program, "u_view_width");
    gl.enable(gl.DEPTH_TEST);
    gl.clearColor(0, 0, 0, 0);
    let currentYaw = DEFAULT_YAW;
    function draw(angle: number) {
      if (disposed || gl!.isContextLost()) return false;
      currentYaw = angle;
      const size = renderSize(
        canvas.clientWidth,
        canvas.clientHeight,
        globalThis.devicePixelRatio ?? 1,
      );
      if (canvas.width !== size.width || canvas.height !== size.height) {
        canvas.width = size.width;
        canvas.height = size.height;
      }
      gl!.viewport(0, 0, size.width, size.height);
      gl!.clear(gl!.COLOR_BUFFER_BIT | gl!.DEPTH_BUFFER_BIT);
      gl!.uniform1f(yaw, currentYaw);
      gl!.uniform1f(aspect, size.width / size.height);
      gl!.uniform1f(halfWidth, viewWidth(size.width / size.height));
      gl!.drawArrays(gl!.TRIANGLES, 0, vertices.length / 9);
      gl!.flush();
      return true;
    }
    canvas.addEventListener("webglcontextlost", lost);
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => {
        try {
          if (!draw(currentYaw)) unavailable();
        } catch {
          unavailable();
        }
      });
      observer.observe(canvas);
    }
    if (!draw(currentYaw)) {
      dispose();
      return null;
    }
    return { draw, dispose };
  } catch {
    dispose();
    return null;
  }
}
