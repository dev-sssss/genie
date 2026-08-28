// Vanilla JS Port of Mesh Text Hover
const MeshText = (function() {
    const GRID_W = 96, GRID_H = 40;
    const DRAG = 1.8, SPRING_K = 0.08, DAMPING = 0.9, DT = 0.1, CHROMA = 0.005;

    const VERT_SRC = `#version 300 es
    in vec2 aPos;
    in vec2 aUv;
    in vec2 aDisp;
    out vec2 vUv;
    out float vMag;
    void main() { gl_Position = vec4(aPos + aDisp, 0.0, 1.0); vUv = aUv; vMag = length(aDisp); }`;

    const FRAG_SRC = `#version 300 es
    precision highp float;
    in vec2 vUv;
    in float vMag;
    out vec4 outColor;
    uniform sampler2D uTex;
    uniform float uChroma;
    uniform vec3 uColorA;
    uniform vec3 uColorB;
    void main() {
        vec4 base = texture(uTex, vUv);
        if (uChroma > 0.0) {
            float o = uChroma * 0.00500 * clamp(vMag * 8.0, 0.0, 1.0);
            float aOff = texture(uTex, vUv + vec2(o, 0.0)).a;
            float bOff = texture(uTex, vUv - vec2(o, 0.0)).a;
            vec3 col = base.rgb * base.a;
            col += uColorA * max(0.0, aOff - base.a);
            col += uColorB * max(0.0, bOff - base.a);
            float aMax = max(base.a, max(aOff, bOff));
            outColor = vec4(col, aMax);
        } else {
            outColor = base;
        }
    }`;

    function compile(gl, type, src) {
        const sh = gl.createShader(type);
        gl.shaderSource(sh, src);
        gl.compileShader(sh);
        if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) return null;
        return sh;
    }
    function linkProgram(gl, vs, fs) {
        const p = gl.createProgram();
        gl.attachShader(p, vs); gl.attachShader(p, fs); gl.linkProgram(p);
        if (!gl.getProgramParameter(p, gl.LINK_STATUS)) return null;
        return p;
    }

    function parseColor(s) {
        if (!s) return [1,1,1];
        if (s.startsWith("#")) {
            let h = s.slice(1);
            if (h.length === 3) h = h.split("").map(c => c+c).join("");
            return [parseInt(h.slice(0,2),16)/255, parseInt(h.slice(2,4),16)/255, parseInt(h.slice(4,6),16)/255];
        }
        return [1,1,1];
    }

    class MeshTextEffect {
        constructor(container, options = {}) {
            this.container = container;
            this.options = { 
                text: "TEXT", color: "#ffffff", fontFamily: "Outfit", fontWeight: 900, 
                fontSize: 120, customColors: ["#40D3FF", "#D0FF07", "#F70824"].map(parseColor), ...options 
            };
            this.canvas = document.createElement("canvas");
            this.canvas.style.display = "block";
            this.canvas.style.width = "100%";
            this.canvas.style.height = "100%";
            this.container.appendChild(this.canvas);
            
            this.gl = this.canvas.getContext("webgl2", { alpha: true, premultipliedAlpha: true, antialias: true });
            if (!this.gl) return;
            
            this.initGL();
        }

        initGL() {
            const gl = this.gl;
            const vertCount = (GRID_W + 1) * (GRID_H + 1);
            this.positions = new Float32Array(vertCount * 2);
            this.uvs = new Float32Array(vertCount * 2);
            for (let y = 0; y <= GRID_H; y++) {
                for (let x = 0; x <= GRID_W; x++) {
                    const i = y * (GRID_W + 1) + x;
                    this.positions[i * 2] = (x / GRID_W) * 2 - 1; 
                    this.positions[i * 2 + 1] = 1 - (y / GRID_H) * 2;
                    this.uvs[i * 2] = x / GRID_W; this.uvs[i * 2 + 1] = y / GRID_H;
                }
            }
            this.indexCount = GRID_W * GRID_H * 6;
            const indices = new Uint32Array(this.indexCount);
            let idx = 0;
            for (let y = 0; y < GRID_H; y++) {
                for (let x = 0; x < GRID_W; x++) {
                    const a = y * (GRID_W + 1) + x, b = a + 1, c = a + (GRID_W + 1), d = c + 1;
                    indices[idx++] = a; indices[idx++] = c; indices[idx++] = b;
                    indices[idx++] = b; indices[idx++] = c; indices[idx++] = d;
                }
            }
            this.disp = new Float32Array(vertCount * 2);
            this.vel = new Float32Array(vertCount * 2);

            const vs = compile(gl, gl.VERTEX_SHADER, VERT_SRC);
            const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG_SRC);
            this.program = linkProgram(gl, vs, fs);

            this.aPos = gl.getAttribLocation(this.program, "aPos");
            this.aUv = gl.getAttribLocation(this.program, "aUv");
            this.aDisp = gl.getAttribLocation(this.program, "aDisp");
            this.uTex = gl.getUniformLocation(this.program, "uTex");
            this.uChroma = gl.getUniformLocation(this.program, "uChroma");
            this.uColorA = gl.getUniformLocation(this.program, "uColorA");
            this.uColorB = gl.getUniformLocation(this.program, "uColorB");

            this.vao = gl.createVertexArray();
            gl.bindVertexArray(this.vao);
            this.posBuf = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuf);
            gl.bufferData(gl.ARRAY_BUFFER, this.positions, gl.STATIC_DRAW);
            gl.enableVertexAttribArray(this.aPos);
            gl.vertexAttribPointer(this.aPos, 2, gl.FLOAT, false, 0, 0);

            this.uvBuf = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, this.uvBuf);
            gl.bufferData(gl.ARRAY_BUFFER, this.uvs, gl.STATIC_DRAW);
            gl.enableVertexAttribArray(this.aUv);
            gl.vertexAttribPointer(this.aUv, 2, gl.FLOAT, false, 0, 0);

            this.dispBuf = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, this.dispBuf);
            gl.bufferData(gl.ARRAY_BUFFER, this.disp, gl.DYNAMIC_DRAW);
            gl.enableVertexAttribArray(this.aDisp);
            gl.vertexAttribPointer(this.aDisp, 2, gl.FLOAT, false, 0, 0);

            const idxBuf = gl.createBuffer();
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, idxBuf);
            gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);

            this.tex = gl.createTexture();
            gl.bindTexture(gl.TEXTURE_2D, this.tex);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

            this.cursor = { x: 99, y: 99, px: 99, py: 99, vx: 0, vy: 0, inside: false };
            
            this.container.addEventListener("pointermove", (e) => {
                const rect = this.canvas.getBoundingClientRect();
                const x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
                const y = 1 - ((e.clientY - rect.top) / rect.height) * 2;
                if (!this.cursor.inside) { this.cursor.px = x; this.cursor.py = y; this.cursor.inside = true; }
                this.cursor.x = x; this.cursor.y = y;
            });
            this.container.addEventListener("pointerleave", () => {
                this.cursor.inside = false; this.cursor.x = 99; this.cursor.y = 99; this.cursor.vx = 0; this.cursor.vy = 0;
            });

            const ro = new ResizeObserver(() => this.resize());
            ro.observe(this.container);
            
            if (document.fonts) {
                document.fonts.ready.then(() => { this.resize(); this.tick(); });
            } else { this.resize(); this.tick(); }
        }

        renderTextToCanvas(w, h) {
            const c = document.createElement("canvas");
            c.width = w; c.height = h;
            const ctx = c.getContext("2d");
            ctx.clearRect(0, 0, w, h);
            ctx.fillStyle = this.options.color;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            const realSize = this.options.fontSize * (window.devicePixelRatio || 1);
            ctx.font = `${this.options.fontWeight} ${realSize}px ${this.options.fontFamily}, sans-serif`;
            
            const lines = this.options.text.split("\\n");
            const lineHeight = realSize * 1.1;
            const startY = (h / 2) - ((lines.length - 1) * lineHeight / 2);
            lines.forEach((line, i) => {
                ctx.fillText(line, w / 2, startY + (i * lineHeight));
            });
            return c;
        }

        resize() {
            const dpr = window.devicePixelRatio || 1;
            const rect = this.container.getBoundingClientRect();
            const w = Math.max(2, Math.round(rect.width * dpr));
            const h = Math.max(2, Math.round(rect.height * dpr));
            if (this.canvas.width !== w || this.canvas.height !== h) {
                this.canvas.width = w; this.canvas.height = h;
                this.gl.viewport(0, 0, w, h);
                const c2 = this.renderTextToCanvas(w, h);
                this.gl.bindTexture(this.gl.TEXTURE_2D, this.tex);
                this.gl.pixelStorei(this.gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
                this.gl.texImage2D(this.gl.TEXTURE_2D, 0, this.gl.RGBA, this.gl.RGBA, this.gl.UNSIGNED_BYTE, c2);
            }
        }

        tick() {
            const gl = this.gl, c = this.cursor;
            c.vx = c.x - c.px; c.vy = c.y - c.py;
            if (Math.hypot(c.vx, c.vy) > 0.3) { c.vx = 0; c.vy = 0; }
            c.px = c.x; c.py = c.y;

            for (let i = 0; i < this.positions.length / 2; i++) {
                const i2 = i * 2;
                const px = this.positions[i2], py = this.positions[i2 + 1];
                const dx = this.disp[i2], dy = this.disp[i2 + 1];
                const cx = c.x - (px + dx), cy = c.y - (py + dy);
                const cd = Math.hypot(cx, cy);
                const proximity = Math.max(0, 1 / (1 + cd / 0.05) - 0.1);

                let vx = this.vel[i2], vy = this.vel[i2 + 1];
                vx += c.vx * DRAG * proximity; vy += c.vy * DRAG * proximity;
                vx -= dx * SPRING_K; vy -= dy * SPRING_K;
                vx *= DAMPING; vy *= DAMPING;
                this.vel[i2] = vx; this.vel[i2 + 1] = vy;
                
                let ndx = dx + vx * DT, ndy = dy + vy * DT;
                if (ndx > 1) ndx = 1; else if (ndx < -1) ndx = -1;
                if (ndy > 1) ndy = 1; else if (ndy < -1) ndy = -1;
                this.disp[i2] = ndx; this.disp[i2 + 1] = ndy;
            }

            gl.bindBuffer(gl.ARRAY_BUFFER, this.dispBuf);
            gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.disp);

            gl.clearColor(0, 0, 0, 0);
            gl.clear(gl.COLOR_BUFFER_BIT);

            gl.useProgram(this.program);
            gl.activeTexture(gl.TEXTURE0);
            gl.bindTexture(gl.TEXTURE_2D, this.tex);
            gl.uniform1i(this.uTex, 0);
            gl.uniform1f(this.uChroma, 1.0);

            const cols = this.options.customColors;
            const cycleMs = 400;
            const idx = Math.floor(performance.now() / cycleMs) % cols.length;
            const cA = cols[idx], cB = cols[(idx + 1) % cols.length];
            gl.uniform3f(this.uColorA, cA[0], cA[1], cA[2]);
            gl.uniform3f(this.uColorB, cB[0], cB[1], cB[2]);

            gl.enable(gl.BLEND);
            gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
            gl.bindVertexArray(this.vao);
            gl.drawElements(gl.TRIANGLES, this.indexCount, gl.UNSIGNED_INT, 0);

            requestAnimationFrame(() => this.tick());
        }
    }

    return MeshTextEffect;
})();
