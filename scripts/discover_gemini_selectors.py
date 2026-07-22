"""Discover actual Gemini DOM selectors using existing session.
Saves results to backend/app/services/gemini_selectors.json
for use by GeminiAutomationService.

Automatically opens the model picker and thinking dropdown
to discover the exact selectors needed.

Usage:
    python scripts/discover_gemini_selectors.py

Requires an existing Gemini login session (cookies / storage state).
"""

import io
import json
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR.resolve()))

from app.core.config import settings
from app.services.fingerprint import build_init_script, generate_fingerprint
from playwright.async_api import async_playwright

SELECTORS_OUTPUT = BACKEND_DIR / "app" / "services" / "gemini_selectors.json"


SCAN_VISIBLE_ELEMENTS = """() => {
    const all = document.querySelectorAll('*');
    const result = [];
    for (const el of all) {
        if (el.offsetParent !== null && el.textContent.trim().length > 0 && el.children.length === 0) {
            let sel = el.tagName.toLowerCase();
            if (el.id) sel += '#' + el.id;
            else if (el.getAttribute('data-test-id')) sel += '[data-test-id="' + el.getAttribute('data-test-id') + '"]';
            else {
                const cls = el.className;
                if (typeof cls === 'string' && cls.trim()) sel += '.' + cls.trim().split(/\\s+/)[0];
            }
            result.push({
                selector: sel,
                tag: el.tagName,
                text: el.textContent.trim().slice(0, 80),
                data_test_id: el.getAttribute('data-test-id') || '',
                class: (el.className || '').slice(0, 80),
                w: el.offsetWidth,
                h: el.offsetHeight,
            });
        }
    }
    return result.slice(0, 200);
}"""


SCAN_MODAL_OPTIONS = """() => {
    // Scan all visible clickable items that appeared after model dropdown opens
    const all = document.querySelectorAll('[role="option"], [role="menuitem"], [role="radio"], [class*="option"], li, button');
    const result = [];
    for (const el of all) {
        if (el.offsetParent !== null) {
            result.push({
                tag: el.tagName,
                role: el.getAttribute('role') || '',
                text: (el.textContent || '').trim().slice(0, 100),
                data_test_id: el.getAttribute('data-test-id') || '',
                class: (el.className || '').slice(0, 100),
                visible: !!el.offsetParent,
                w: el.offsetWidth,
                h: el.offsetHeight,
            });
        }
    }
    return result;
}"""


async def discover():
    session_path = Path(settings.gemini_session_path)

    if not session_path.exists():
        print(f"ERROR: Session file not found at {session_path}")
        print("Please run a manual login session first.")
        sys.exit(1)

    raw = session_path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
    is_storage_state = isinstance(parsed, dict) and "cookies" in parsed
    is_cookies_only = isinstance(parsed, list) or (isinstance(parsed, dict) and "name" in parsed)

    async with async_playwright() as pw:
        seed = hash(str(time.time()))
        fp = generate_fingerprint(str(seed))
        stealth_js = build_init_script(fp)

        launch_kwargs = {
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
            ],
        }

        browser = await pw.chromium.launch(**launch_kwargs)

        ctx_kwargs = {
            "viewport": {"width": 1280, "height": 800},
            "locale": "vi-VN",
            "timezone_id": "Asia/Ho_Chi_Minh",
        }

        if is_storage_state:
            ctx_kwargs["storage_state"] = str(session_path)
        elif is_cookies_only:
            print("  (cookies-only file)")

        context = await browser.new_context(**ctx_kwargs)
        await context.add_init_script(stealth_js)

        if is_cookies_only and not is_storage_state:
            cookies_raw = json.loads(raw)
            cookies_list = cookies_raw if isinstance(cookies_raw, list) else [cookies_raw]
            await context.add_cookies(cookies_list)

        page = await context.new_page()
        page.set_default_timeout(30000)

        print(f"Navigating to {settings.gemini_url} ...")
        await page.goto(settings.gemini_url, wait_until="load", timeout=60000)
        # wait for page to settle — networkidle can hang on Gemini's persistent connections
        await page.wait_for_timeout(10000)

        # ─────────────────────────────────────────────────────
        # DISCOVERY PHASE 1: Find the model selector button
        # ─────────────────────────────────────────────────────
        print("\n=== PHASE 1: Scanning page elements ===")
        all_elements = await page.evaluate(SCAN_VISIBLE_ELEMENTS)

        model_btn = None
        for el in all_elements:
            t = el["text"].lower()
            if "flash" in t or "model" in t or t.startswith("gemini"):
                print(f"  POTENTIAL MODEL BTN: data-test-id='{el['data_test_id']}' text='{el['text']}' class='{el['class']}'")
                if el["data_test_id"] in ("bard-mode-menu-button", "mode-menu-button"):
                    model_btn = el

        if not model_btn:
            for el in all_elements:
                if el["data_test_id"] in ("bard-mode-menu-button", "mode-menu-button"):
                    model_btn = el
                    break

        if not model_btn:
            # Try finding by class pattern: picker-primary-text + parent button
            for el in all_elements:
                if "picker-primary-text" in el["class"] and any(w in el["text"].lower() for w in ["flash", "pro", "gemini"]):
                    model_btn = el
                    print(f"  -> Using model button by class: text='{el['text']}' class='{el['class']}'")
                    break

        if not model_btn:
            # Try finding by parent container of Flash text
            print("  Trying JS approach to find model button parent...")
            parent_info = await page.evaluate("""() => {
                const spans = document.querySelectorAll('span.picker-primary-text');
                for (const s of spans) {
                    if (s.textContent.toLowerCase().includes('flash')) {
                        let p = s.parentElement;
                        let depth = 0;
                        while (p && depth < 10) {
                            const tag = p.tagName;
                            const role = p.getAttribute('role') || '';
                            const did = p.getAttribute('data-test-id') || '';
                            if (tag === 'BUTTON' || role === 'button' || did) {
                                return {
                                    text: p.textContent.trim().slice(0, 100),
                                    tag: tag,
                                    data_test_id: did,
                                    class_name: (p.className || '').slice(0, 100),
                                    id: p.id || '',
                                    depth: depth,
                                };
                            }
                            p = p.parentElement;
                            depth++;
                        }
                        return { text: s.textContent.trim().slice(0, 100), tag: 'SPAN' };
                    }
                }
                return null;
            }""")
            if parent_info:
                print(f"  -> Found model button parent: {parent_info}")
                model_btn = parent_info

        if not model_btn:
            print("  ERROR: Could not find model button")
            await browser.close()
            return

        print(f"\n  Found model button: data-test-id='{model_btn.get('data_test_id', '')}' text='{model_btn.get('text', '')}'")

        # ─────────────────────────────────────────────────────
        # DISCOVERY PHASE 2: Click model button, scan options
        # ─────────────────────────────────────────────────────
        print("\n=== PHASE 2: Opening model picker ===")
        model_selected_text = model_btn.get("text", "Flash-Lite")

        # First, click the model pill at the top (the one showing "Flash-Lite")
        # Use JS to find and click the correct parent button/container
        await page.evaluate("""(() => {
            const pills = document.querySelectorAll('[data-test-id*="mode-menu"], .picker-primary-text');
            for (const p of pills) {
                let container = p.parentElement;
                while (container && container.tagName !== 'BUTTON' &&
                       container.tagName !== 'DIV' &&
                       !(container.getAttribute('role') || '').includes('button')) {
                    container = container.parentElement;
                }
                if (container) {
                    container.click();
                    return true;
                }
            }
            const all = document.querySelectorAll('span, button, div');
            for (const el of all) {
                if (el.textContent.trim() === 'Flash-Lite' && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            return false;
        })()""")
        await page.wait_for_timeout(3000)

        print("  Scanning options after first click...")
        model_options = await page.evaluate(SCAN_MODAL_OPTIONS)
        print(f"\n  Options after first click:")
        for opt in model_options:
            t = opt["text"].strip()
            if t:
                print(f"    role={opt['role']} text='{t}' data-test-id='{opt['data_test_id']}'")

        # Now try clicking bard-mode-menu-button if it appeared (it's in the sidebar panel)
        bard_btn = page.locator('[data-test-id="bard-mode-menu-button"]').first
        if await bard_btn.count() > 0:
            print("\n  Found bard-mode-menu-button, clicking it to open model picker...")
            await bard_btn.click()
            await page.wait_for_timeout(2000)
            model_options = await page.evaluate(SCAN_MODAL_OPTIONS)
            print(f"\n  Options after second click (model picker):")
            for opt in model_options:
                t = opt["text"].strip()
                if t:
                    print(f"    role={opt['role']} text='{t}' data-test-id='{opt['data_test_id']}'")
        await page.wait_for_timeout(2000)

        model_options = await page.evaluate(SCAN_MODAL_OPTIONS)
        print(f"\n  Options found after clicking model button:")
        for opt in model_options:
            t = opt["text"].strip()
            if t and len(t) > 3:
                print(f"    role={opt['role']} text='{t}' data-test-id='{opt['data_test_id']}'")

        # Try to find "2.5 Flash" or "3.5 Flash" option
        target_model = None
        for opt in model_options:
            t = opt["text"].lower()
            if ("2.5" in t or "3.5" in t) and "flash" in t:
                target_model = opt
                break
        if not target_model:
            for opt in model_options:
                t = opt["text"].lower()
                if "flash" in t and ("2" in t or "3" in t):
                    target_model = opt
                    break
        if not target_model:
            for opt in model_options:
                t = opt["text"].lower()
                if "gemini" in t and "flash" in t:
                    target_model = opt
                    break

        if target_model:
            print(f"\n  Clicking model option: '{target_model['text']}'")
            opt_text = target_model["text"].strip()
            # Try with role="menuitem" first (the actual role)
            option_el = page.locator(f'[role="menuitem"]:has-text("{opt_text[:30]}")').first
            if await option_el.count() == 0:
                option_el = page.locator(f'text="{opt_text[:30]}"').first
            if await option_el.count() > 0:
                await option_el.click()
                await page.wait_for_timeout(2000)
                print("  Model selected successfully")
                model_selected_text = target_model["text"]
            else:
                print("  Could not click model option (locator not found)")
                model_selected_text = model_btn.get("text", "Flash-Lite")
        else:
            print("  No 2.5/3.5 Flash model option found")
            model_selected_text = model_btn.get("text", "Flash-Lite")

        # ─────────────────────────────────────────────────────
        # DISCOVERY PHASE 3: Re-open panel & investigate thinking + all elements
        # ─────────────────────────────────────────────────────
        print(f"\n=== PHASE 3: Re-opening panel for thinking level discovery ===")

        # Re-open model picker: click sidebar pill
        await page.evaluate("""(() => {
            const s = document.querySelector('span.picker-primary-text');
            if (s) {
                let p = s.parentElement;
                while (p && p.tagName !== 'BUTTON') p = p.parentElement;
                if (p) { p.click(); return true; }
            }
            return false;
        })()""")
        await page.wait_for_timeout(2000)
        # Click bard-mode-menu-button inside sidebar panel
        bard_btn2 = page.locator('[data-test-id="bard-mode-menu-button"]').first
        if await bard_btn2.count() > 0:
            await bard_btn2.click()
            await page.wait_for_timeout(2000)

        # Now scan ALL elements inside the popup that has model options
        print("\n  Scanning ALL elements in the picker popup...")
        all_in_picker = await page.evaluate("""() => {
            const result = [];
            // Find the picker popup container
            const menuitems = document.querySelectorAll('[role="menuitem"]');
            let popup = null;
            for (const m of menuitems) {
                if (m.offsetParent !== null) {
                    popup = m.closest('[role="listbox"], [role="menu"], [role="dialog"]');
                    if (popup) break;
                }
            }
            if (!popup) {
                // Fallback: get all visible elements that appeared recently
                const all = document.querySelectorAll('div, span, button, [role]');
                for (const el of all) {
                    if (el.offsetParent !== null && (el.textContent || '').trim().length > 0 && el.children.length < 5) {
                        result.push({
                            text: (el.textContent || '').trim().slice(0, 80),
                            tag: el.tagName,
                            role: el.getAttribute('role') || '',
                            data_test_id: el.getAttribute('data-test-id') || '',
                        });
                    }
                }
                return result;
            }
            const items = popup.querySelectorAll('*');
            for (const el of items) {
                if (el.offsetParent !== null && (el.textContent || '').trim().length > 0 && el.children.length < 4) {
                    result.push({
                        text: (el.textContent || '').trim().slice(0, 80),
                        tag: el.tagName,
                        role: el.getAttribute('role') || '',
                        data_test_id: el.getAttribute('data-test-id') || '',
                    });
                }
            }
            return result;
        }""")

        # Deduplicate
        seen = set()
        unique_items = []
        for item in all_in_picker:
            key = (item['text'], item['role'])
            if key not in seen:
                seen.add(key)
                unique_items.append(item)

        print(f"\n  All items in picker popup ({len(unique_items)} unique):")
        for item in unique_items:
            t = item['text']
            if len(t) > 0:
                print(f"    text='{t}' tag={item['tag']} role={item['role']} data-test-id='{item['data_test_id']}'")

        # Try finding and clicking the thinking level row
        thinking_row = None
        for item in unique_items:
            if 'tư duy' in item['text'].lower():
                thinking_row = item
                break
        if not thinking_row:
            for item in unique_items:
                if 'tiêu chuẩn' in item['text'].lower() or 'standard' in item['text'].lower():
                    thinking_row = item
                    break

        if thinking_row and thinking_row['data_test_id']:
            print(f"\n  Trying to click thinking level by data-test-id: '{thinking_row['data_test_id']}'")
            btn = page.locator(f'[data-test-id="{thinking_row["data_test_id"]}"]').first
            if await btn.count() > 0:
                await btn.click()
                await page.wait_for_timeout(2000)
                print("  Clicked, scanning for 'Mở rộng'...")

        # As last resort: directly try clicking the text "Cấp độ tư duy" if found
        print("\n  Directly trying to click 'Cấp độ tư duy' element...")
        try:
            td_item = page.locator('text="Cấp độ tư duy"').first
            if await td_item.count() > 0:
                await td_item.click()
                await page.wait_for_timeout(2000)
                print("  Clicked 'Cấp độ tư duy', scanning for sub-options...")
                after_click = await page.evaluate("""() => {
                    const result = [];
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        if (el.offsetParent !== null) {
                            const t = (el.textContent || '').trim();
                            if (!t || t.length > 70) continue;
                            const tl = t.toLowerCase();
                            if (tl.includes('mở rộng') || tl.includes('extended') ||
                                tl.includes('nâng cao') ||
                                (tl.includes('tiêu chuẩn') && !tl.includes('cấp độ'))) {
                                result.push({
                                    text: t.slice(0, 60),
                                    tag: el.tagName,
                                    role: el.getAttribute('role') || '',
                                    data_test_id: el.getAttribute('data-test-id') || '',
                                });
                            }
                        }
                    }
                    return result;
                }""")
                print(f"\n  After clicking 'Cấp độ tư duy':")
                for item in after_click:
                    print(f"    text='{item['text']}' tag={item['tag']} role={item['role']} data-test-id='{item['data_test_id']}'")
        except Exception as e:
            print(f"  Exception: {e}")

        # ─────────────────────────────────────────────────────
        # SAVE RESULTS
        # ─────────────────────────────────────────────────────
        print(f"\n=== PHASE 4: Saving selectors ===")

        model_selector_str = '[data-test-id="bard-mode-menu-button"]' if model_btn.get("data_test_id") != "bard-mode-menu-button" else '.picker-primary-text'
        output = {
            "model_selector": model_selector_str,
            "model_current_text": model_selected_text,
            "model_options_raw": [{"text": o["text"], "data_test_id": o["data_test_id"], "role": o["role"], "class": o.get("class", "")} for o in model_options if o["text"].strip()],
            "discovered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        SELECTORS_OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSelectors saved to {SELECTORS_OUTPUT}")

        # Keep browser open for 30 seconds so user can see the result
        print("\nBrowser will close in 10 seconds...")
        await page.wait_for_timeout(10000)
        await browser.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(discover())
