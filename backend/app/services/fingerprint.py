from __future__ import annotations

import random
from typing import Any

USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
]

WINDOW_SIZES = [
    (1366, 768),
    (1440, 900),
    (1536, 864),
    (1600, 900),
    (1680, 1050),
    (1920, 1080),
    (1280, 720),
    (1280, 800),
    (1920, 1200),
]

LANG_POOL = [
    ["en-US", "en"],
    ["en-GB", "en"],
    ["en-AU", "en"],
    ["en-CA", "en"],
    ["vi-VN", "vi", "en-US", "en"],
]

WEBGL_POOL: list[tuple[str, str]] = [
    ("Intel Inc.", "Intel Iris OpenGL Engine"),
    ("Intel Inc.", "Intel(R) UHD Graphics 620"),
    ("Intel Inc.", "Intel(R) Iris(TM) Plus Graphics 640"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 4060 OpenGL Engine"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 3060 OpenGL Engine"),
    ("NVIDIA Corporation", "NVIDIA GeForce GTX 1660 Ti OpenGL Engine"),
    ("Google Inc.", "Google SwiftShader"),
    ("AMD", "AMD Radeon(TM) Graphics"),
]


def generate_fingerprint(seed: str) -> dict[str, Any]:
    rng = random.Random(seed)
    w, h = rng.choice(WINDOW_SIZES)
    vendor, renderer = rng.choice(WEBGL_POOL)
    langs = rng.choice(LANG_POOL)
    return {
        "user_agent": rng.choice(USER_AGENT_POOL),
        "window_width": w,
        "window_height": h,
        "lang": langs[0],
        "languages": langs,
        "hardware_concurrency": rng.choice([2, 4, 6, 8]),
        "webgl_vendor": vendor,
        "webgl_renderer": renderer,
        "canvas_noise": round(rng.uniform(0.0001, 0.002), 6),
    }


def build_init_script(fp: dict[str, Any]) -> str:
    langs_json = __import__("json").dumps(fp["languages"])
    concurrency = fp["hardware_concurrency"]
    vendor = fp["webgl_vendor"]
    renderer = fp["webgl_renderer"]
    noise = fp["canvas_noise"]

    return f"""
(() => {{
    const wp = Object.getOwnPropertyDescriptor;
    const def = Object.defineProperty;

    // navigator.webdriver
    def(navigator, 'webdriver', {{ get: () => undefined }});

    // navigator.hardwareConcurrency
    def(navigator, 'hardwareConcurrency', {{ get: () => {concurrency} }});

    // navigator.languages
    def(navigator, 'languages', {{ get: () => {langs_json} }});
    def(navigator, 'language', {{ get: () => '{fp["lang"]}' }});

    // chrome.runtime
    if (!window.chrome) {{
        window.chorem = {{
            runtime: {{}},
            loadTimes: function() {{}},
            csi: function() {{}},
            app: {{}}
        }};
    }}

    // Plugins
    const origPlugins = navigator.plugins;
    def(navigator, 'plugins', {{
        get: () => {{
            if (origPlugins.length > 0) return origPlugins;
            const arr = [
                {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' }},
                {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' }},
                {{ name: 'Widevine Content Decryption Module', filename: 'widevinecdm.dll' }}
            ];
            arr.item = i => arr[i];
            arr.namedItem = n => arr.find(p => p.name === n);
            arr.length = arr.length;
            return arr;
        }}
    }});

    // WebGL vendor/renderer
    const origGetParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {{
        if (p === 37445) return '{vendor}';
        if (p === 37446) return '{renderer}';
        return origGetParam.call(this, p);
    }};
    const origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(p) {{
        if (p === 37445) return '{vendor}';
        if (p === 37446) return '{renderer}';
        return origGetParam2.call(this, p);
    }};

    // Canvas noise
    const noise = {noise};
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function(x, y, w, h) {{
        const img = origGetImageData.call(this, x, y, w, h);
        for (let i = 0; i < img.data.length; i += 4) {{
            img.data[i] += (Math.random() - 0.5) * noise * 255;
            img.data[i+1] += (Math.random() - 0.5) * noise * 255;
            img.data[i+2] += (Math.random() - 0.5) * noise * 255;
        }}
        return img;
    }};
}})();
"""
