import base64
import io
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from parser import parse_pdf_coupons

BASE_DIR = Path(__file__).parent
DP_PDF = Path(
    r"C:\Users\andri_gxiil3v\.gemini\antigravity\brain\f3bed7ec-96d7-4fc6-9bd1-d25f649920ff\.user_uploaded\media_1795457884223_d97f4a65.pdf"
)
A95_PDF = Path(
    r"C:\Users\andri_gxiil3v\.gemini\antigravity\brain\f3bed7ec-96d7-4fc6-9bd1-d25f649920ff\.user_uploaded\media_1795458776608_73aa7cc5.pdf"
)
CRM_HTML_PATH = Path(
    r"C:\Users\andri_gxiil3v\.gemini\antigravity\brain\f3bed7ec-96d7-4fc6-9bd1-d25f649920ff\scratch\crm_page\База паливних талонів — TermoUnion.htm"
)

EXT_DIR = BASE_DIR / "extension"


def verify_png_data_url(data_url: str) -> tuple[int, int]:
    assert data_url.startswith("data:image/png;base64,"), "Invalid photo_data URI prefix"
    raw = base64.b64decode(data_url.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw))
    img.verify()
    img = Image.open(io.BytesIO(raw))
    w, h = img.size
    assert max(w, h) >= 950, f"Image too small for CRM QR check: {w}x{h}"
    return w, h


def run_python_parser_tests():
    print("=== [Part A] Testing Python parser.py on real PDFs ===")
    cases = [
        ("DP_PDF", DP_PDF, 37, "ДП", 99999600000025241324),
        ("A95_PDF", A95_PDF, 100, "А-95", 99999600000025240768),
    ]
    for name, path, expected_count, expected_fuel, first_serial in cases:
        t0 = time.perf_counter()
        coupons = parse_pdf_coupons(path.read_bytes())
        dt = time.perf_counter() - t0
        assert len(coupons) == expected_count, f"{name}: expected {expected_count}, got {len(coupons)}"

        for i, c in enumerate(coupons):
            exp_serial = str(first_serial + i)
            assert c["fuel_type"] == expected_fuel, f"{name}[{i}] fuel_type={c['fuel_type']}"
            assert c["azs"] == "ОККО", f"{name}[{i}] azs={c['azs']}"
            assert c["nominal"] == "10", f"{name}[{i}] nominal={c['nominal']}"
            assert c["expires_at"] == "2026-12-23", f"{name}[{i}] expires_at={c['expires_at']}"
            assert c["quantity"] == 1, f"{name}[{i}] quantity={c['quantity']}"
            assert c["serial_number"] == exp_serial, f"{name}[{i}] serial={c['serial_number']} != {exp_serial}"
            verify_png_data_url(c["image_base64"])

        print(f"  [OK] {name}: {len(coupons)} coupons parsed & verified in {dt:.2f}s "
              f"(first={coupons[0]['serial_number']}, last={coupons[-1]['serial_number']}, "
              f"size={coupons[0]['width']}x{coupons[0]['height']})")


def start_mock_crm_server():
    raw_html = CRM_HTML_PATH.read_text(encoding="utf-8", errors="replace")
    # Rewrite remote form action & links to local paths, drop external assets for offline speed
    raw_html = raw_html.replace('action="https://driver.tun.com.ua/admin/tickets"', 'action="/admin/tickets"')
    raw_html = raw_html.replace('href="https://driver.tun.com.ua/admin/tickets/export"', 'href="/admin/tickets/export"')
    raw_html = raw_html.replace("https://driver.tun.com.ua/admin/tickets?page=13", "/admin/tickets?page=1")
    raw_html = raw_html.replace("https://driver.tun.com.ua/admin/tickets?page=2", "/admin/tickets?page=1")
    raw_html = raw_html.replace("https://driver.tun.com.ua/admin/tickets?page=3", "/admin/tickets?page=1")
    raw_html = raw_html.replace("./База паливних талонів — TermoUnion_files/app.css", "/empty.css")
    raw_html = raw_html.replace("./База паливних талонів — TermoUnion_files/app.js.завантаження", "/empty.js")
    raw_html = raw_html.replace("./База паливних талонів — TermoUnion_files/logo.png", "/empty.png")

    state = {
        "submissions": [],
        "current_token": "bb44ca7dde6fb8a24576f33aaa5298e45f081e1d0991b9141f6a083b6b6d044c",
        "export_enabled": True,
        "export_csv": "ID;Номер талона;Пальне\n",
        "db_pages": {},      # {page_num: [serial, ...]}
        "search_db": [],     # [serial, ...]
        "record_to_db": False,
        "lock": threading.Lock(),
    }

    def render_rows_html(items):
        out = []
        for item in items:
            if isinstance(item, tuple):
                s, status = item
            else:
                s, status = item, "У базі"
            out.append(
                f'<tr><td><a class="cell-link" href="/admin/tickets/1/edit"><strong>{s}</strong></a></td>'
                f'<td><span class="badge">{status}</span></td></tr>'
            )
        return "".join(out)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # silence HTTP access logs

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/admin/tickets/export":
                if not state["export_enabled"]:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = state["export_csv"].encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/admin/tickets":
                q_val = (qs.get("q") or [""])[0].strip()
                page_val = int((qs.get("page") or ["1"])[0])

                if q_val:
                    matched = [s for s in state["search_db"] if q_val in s]
                    html = f'<html><body><table class="data-table"><tbody>{render_rows_html(matched)}</tbody></table></body></html>'
                elif page_val > 1:
                    serials = state["db_pages"].get(page_val, [])
                    html = f'<html><body><table class="data-table"><tbody>{render_rows_html(serials)}</tbody></table></body></html>'
                else:
                    html = raw_html.replace(
                        "bb44ca7dde6fb8a24576f33aaa5298e45f081e1d0991b9141f6a083b6b6d044c",
                        state["current_token"],
                    )
                    max_p = max(state["db_pages"].keys(), default=1)
                    if max_p > 1:
                        pag_links = "".join(
                            f'<a class="page-btn" href="/admin/tickets?page={p}">{p}</a>'
                            for p in range(1, max_p + 1)
                        )
                        html = html.replace(
                            '<nav class="pagination" aria-label="Навігація сторінками">',
                            f'<nav class="pagination" aria-label="Навігація сторінками">{pag_links}',
                        )
                    p1_extra = state["db_pages"].get(1, [])
                    if p1_extra:
                        html = html.replace("<tbody>", f"<tbody>{render_rows_html(p1_extra)}", 1)

                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path.endswith(".css"):
                self.send_response(200)
                self.send_header("Content-Type", "text/css")
                self.end_headers()
            elif parsed.path.endswith(".js"):
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.end_headers()
            else:
                self.send_response(204)
                self.end_headers()

        def do_POST(self):
            if self.path != "/admin/tickets":
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")
            parsed = urllib.parse.parse_qs(raw_body, keep_blank_values=True)
            flat = {k: v[0] if v else "" for k, v in parsed.items()}

            with state["lock"]:
                expected_tok = state["current_token"]
                if flat.get("_token") != expected_tok:
                    self.send_response(419)
                    self.end_headers()
                    self.wfile.write(b"CSRF token mismatch")
                    return

                state["submissions"].append(flat)
                if state["record_to_db"] and flat.get("serial_number"):
                    ser = flat["serial_number"]
                    if ser not in state["search_db"]:
                        state["search_db"].append(ser)
                    state["db_pages"].setdefault(1, []).append(ser)
                next_tok = f"lab_token_{len(state['submissions'])}"
                state["current_token"] = next_tok

            resp_html = f'<html><body><input type="hidden" name="_token" value="{next_tok}">OK</body></html>'.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(resp_html)))
            self.end_headers()
            self.wfile.write(resp_html)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, state


def inject_extension(page):
    page.add_script_tag(path=str(EXT_DIR / "lib" / "pdf.worker.min.js"))
    page.add_script_tag(path=str(EXT_DIR / "lib" / "pdf.min.js"))
    page.add_script_tag(path=str(EXT_DIR / "content.js"))
    page.evaluate("() => { window.confirm = () => true; window.alert = (m) => { throw new Error('Unexpected alert: ' + m); }; }")


def launch_browser(p):
    for channel in ("chrome", "msedge", None):
        try:
            kwargs = {"headless": True}
            if channel:
                kwargs["channel"] = channel
            return p.chromium.launch(**kwargs)
        except Exception:
            continue
    raise RuntimeError("Could not launch Chrome, Edge, or Chromium via Playwright.")


def run_extension_e2e_tests():
    print("=== [Part B] Testing Chrome Extension E2E with Mock CRM Server ===")
    server, state = start_mock_crm_server()
    port = server.server_address[1]
    crm_url = f"http://127.0.0.1:{port}/admin/tickets"

    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            page = browser.new_page(viewport={"width": 1366, "height": 900})

            console_errors = []
            page.on("pageerror", lambda err: console_errors.append(str(err)))

            # --- Scenario 1: DP PDF (37 coupons, auto-detect without clicking pill first) ---
            page.goto(crm_url, wait_until="domcontentloaded")
            inject_extension(page)

            page.click("#talonauto-open-btn")
            file_input = page.locator("#talonauto-host >> #fileInput")
            file_input.set_input_files(str(DP_PDF))

            page.wait_for_function(
                """() => {
                    const host = document.getElementById('talonauto-host');
                    if (!host || !host.shadowRoot) return false;
                    return host.shadowRoot.querySelectorAll('#tbody tr').length === 37;
                }""",
                timeout=30_000,
            )

            dp_rows = page.evaluate("""() => {
                const sr = document.getElementById('talonauto-host').shadowRoot;
                const activePill = sr.querySelector('.fuel-pill.active')?.dataset?.fuel || '';
                const rows = Array.from(sr.querySelectorAll('#tbody tr')).map(tr => ({
                    fuel_type: tr.querySelector('[data-k="fuel_type"]').value,
                    azs: tr.querySelector('[data-k="azs"]').value,
                    nominal: tr.querySelector('[data-k="nominal"]').value,
                    expires_at: tr.querySelector('[data-k="expires_at"]').value,
                    quantity: tr.querySelector('[data-k="quantity"]').value,
                    serial_number: tr.querySelector('[data-k="serial_number"]').value,
                }));
                return { activePill, rows };
            }""")

            assert dp_rows["activePill"] == "ДП", f"Expected auto-active ДП pill, got {dp_rows['activePill']}"
            assert len(dp_rows["rows"]) == 37
            for i, r in enumerate(dp_rows["rows"]):
                exp_serial = str(99999600000025241324 + i)
                assert r["fuel_type"] == "ДП", f"DP row {i} fuel={r['fuel_type']}"
                assert r["azs"] == "ОККО", f"DP row {i} azs={r['azs']}"
                assert r["nominal"] == "10", f"DP row {i} nominal={r['nominal']}"
                assert r["expires_at"] == "2026-12-23", f"DP row {i} exp={r['expires_at']}"
                assert r["quantity"] == "1", f"DP row {i} qty={r['quantity']}"
                assert r["serial_number"] == exp_serial, f"DP row {i} serial={r['serial_number']}"

            # Submit all 37 to mock CRM
            page.locator("#talonauto-host >> #uploadBtn").click()
            page.wait_for_function(
                """() => {
                    const sr = document.getElementById('talonauto-host')?.shadowRoot;
                    return sr && sr.getElementById('statusText')?.textContent.includes('Готово! Додано: 37, помилок: 0');
                }""",
                timeout=30_000,
            )

            assert len(state["submissions"]) == 37, f"Expected 37 POSTs, got {len(state['submissions'])}"
            for i, sub in enumerate(state["submissions"]):
                assert sub["fuel_type"] == "ДП"
                assert sub["azs"] == "ОККО"
                assert sub["nominal"] == "10"
                assert sub["expires_at"] == "2026-12-23"
                assert sub["quantity"] == "1"
                assert sub["serial_number"] == str(99999600000025241324 + i)
                verify_png_data_url(sub["photo_data"])
            print("  [OK] Extension E2E DP_PDF: 37/37 rows parsed (incl. 1x1 page 5) & POSTed cleanly")

            # --- Scenario 2: A95 PDF (100 coupons, explicit Step 1 pill click before upload) ---
            state["submissions"].clear()
            page.goto(crm_url, wait_until="domcontentloaded")
            inject_extension(page)

            page.click("#talonauto-open-btn")
            page.locator('#talonauto-host >> .fuel-pill[data-fuel="А-95"]').click()
            page.locator("#talonauto-host >> #fileInput").set_input_files(str(A95_PDF))

            page.wait_for_function(
                """() => {
                    const host = document.getElementById('talonauto-host');
                    if (!host || !host.shadowRoot) return false;
                    return host.shadowRoot.querySelectorAll('#tbody tr').length === 100;
                }""",
                timeout=60_000,
            )

            a95_rows = page.evaluate("""() => {
                const sr = document.getElementById('talonauto-host').shadowRoot;
                return Array.from(sr.querySelectorAll('#tbody tr')).map(tr => ({
                    fuel_type: tr.querySelector('[data-k="fuel_type"]').value,
                    azs: tr.querySelector('[data-k="azs"]').value,
                    nominal: tr.querySelector('[data-k="nominal"]').value,
                    expires_at: tr.querySelector('[data-k="expires_at"]').value,
                    quantity: tr.querySelector('[data-k="quantity"]').value,
                    serial_number: tr.querySelector('[data-k="serial_number"]').value,
                }));
            }""")

            assert len(a95_rows) == 100
            for i, r in enumerate(a95_rows):
                exp_serial = str(99999600000025240768 + i)
                assert r["fuel_type"] == "А-95", f"A95 row {i} fuel={r['fuel_type']}"
                assert r["azs"] == "ОККО", f"A95 row {i} azs={r['azs']}"
                assert r["nominal"] == "10", f"A95 row {i} nominal={r['nominal']}"
                assert r["expires_at"] == "2026-12-23", f"A95 row {i} exp={r['expires_at']}"
                assert r["quantity"] == "1", f"A95 row {i} qty={r['quantity']}"
                assert r["serial_number"] == exp_serial, f"A95 row {i} serial={r['serial_number']}"

            page.locator("#talonauto-host >> #uploadBtn").click()
            page.wait_for_function(
                """() => {
                    const sr = document.getElementById('talonauto-host')?.shadowRoot;
                    return sr && sr.getElementById('statusText')?.textContent.includes('Готово! Додано: 100, помилок: 0');
                }""",
                timeout=60_000,
            )

            assert len(state["submissions"]) == 100, f"Expected 100 POSTs, got {len(state['submissions'])}"
            for i, sub in enumerate(state["submissions"]):
                assert sub["fuel_type"] == "А-95"
                assert sub["azs"] == "ОККО"
                assert sub["nominal"] == "10"
                assert sub["expires_at"] == "2026-12-23"
                assert sub["quantity"] == "1"
                assert sub["serial_number"] == str(99999600000025240768 + i)
                verify_png_data_url(sub["photo_data"])
            print("  [OK] Extension E2E A95_PDF: 100/100 rows parsed (incl. 1x1 page 12) & POSTed cleanly")

            # Helper to run PDF import and inspect duplicate state in Shadow DOM
            def import_pdf_and_get_dups(pdf_path, expected_count):
                page.goto(crm_url, wait_until="domcontentloaded")
                inject_extension(page)
                page.click("#talonauto-open-btn")
                page.locator("#talonauto-host >> #fileInput").set_input_files(str(pdf_path))
                page.wait_for_function(
                    f"""() => {{
                        const host = document.getElementById('talonauto-host');
                        if (!host || !host.shadowRoot) return false;
                        return host.shadowRoot.querySelectorAll('#tbody tr').length === {expected_count};
                    }}""",
                    timeout=60_000,
                )
                return page.evaluate("""() => {
                    const sr = document.getElementById('talonauto-host').shadowRoot;
                    return {
                        counterText: sr.getElementById('dupCounter').textContent.trim(),
                        dbBadge: sr.getElementById('dbCountBadge').textContent.trim(),
                        dupSerials: Array.from(sr.querySelectorAll('#tbody tr.is-duplicate'))
                            .map(tr => tr.querySelector('[data-k="serial_number"]').value),
                        dupTags: Array.from(sr.querySelectorAll('#tbody tr.is-duplicate .dup-tag'))
                            .map(el => el.textContent.trim()),
                    };
                }""")

            # --- DB Test 1: Paginated DB Table (Page 2 Issued + Page 3 Used, CSV export disabled) ---
            state["export_enabled"] = False
            state["db_pages"] = {
                2: [("99999600000025241326", "Активний")],
                3: [("99999600000025241340", "Використано")],
            }
            state["search_db"] = []
            res1 = import_pdf_and_get_dups(DP_PDF, 37)
            assert res1["counterText"] == "⚠️ Задубльовані: 2", f"DB Test 1 counter={res1['counterText']}"
            assert res1["dupSerials"] == ["99999600000025241326", "99999600000025241340"], res1["dupSerials"]
            assert res1["dupTags"] == ["ВЖЕ Є В БАЗІ (Активний)", "ВЖЕ Є В БАЗІ (Використано)"], res1["dupTags"]
            print(f"  [OK] DB Test 1 (Paginated DB pages 2 Активний & 3 Використано): {res1['counterText']} ({res1['dbBadge']})")

            # --- DB Test 2: Tricky CSV Export ("ID талона" column + Excel ="..." escaping) + Bulk Checkboxes ---
            state["export_enabled"] = True
            state["db_pages"] = {}
            state["search_db"] = []
            state["export_csv"] = (
                '"ID талона";"Серійний номер";"Пальне"\n'
                '"101";"99999600000025241324";"ДП"\n'
                '"102";"99999600000025241335";"ДП"\n'
                '"103";="99999600000025241360";"ДП"\n'
            )
            res2 = import_pdf_and_get_dups(DP_PDF, 37)
            assert res2["counterText"] == "⚠️ Задубльовані: 3", f"DB Test 2 counter={res2['counterText']}"
            assert res2["dupSerials"] == [
                "99999600000025241324",
                "99999600000025241335",
                "99999600000025241360",
            ], res2["dupSerials"]

            page.locator("#talonauto-host >> #removeDupsBtn").click()
            after_remove = page.evaluate("""() => {
                const sr = document.getElementById('talonauto-host').shadowRoot;
                return {
                    rowCount: sr.querySelectorAll('#tbody tr').length,
                    counterText: sr.getElementById('dupCounter').textContent.trim(),
                    dupRowCount: sr.querySelectorAll('#tbody tr.is-duplicate').length,
                };
            }""")
            assert after_remove["rowCount"] == 34, f"Expected 34 rows after removing 3 dups, got {after_remove['rowCount']}"
            assert after_remove["counterText"] == "✓ Задубльовані: 0", after_remove["counterText"]
            assert after_remove["dupRowCount"] == 0

            # Multi-select checkboxes: pick 2 rows, delete them, then Select All and delete remaining 32
            page.locator("#talonauto-host >> .row-check").nth(0).check()
            page.locator("#talonauto-host >> .row-check").nth(1).check()
            sel2_btn = page.locator("#talonauto-host >> #deleteSelectedBtn").text_content().strip()
            assert sel2_btn == "🗑️ Видалити вибрані (2)", f"Unexpected delete button text: {sel2_btn}"
            page.locator("#talonauto-host >> #deleteSelectedBtn").click()
            assert page.locator("#talonauto-host >> #tbody tr").count() == 32

            page.locator("#talonauto-host >> #checkAllRows").check()
            sel32_btn = page.locator("#talonauto-host >> #deleteSelectedBtn").text_content().strip()
            assert sel32_btn == "🗑️ Видалити вибрані (32)", f"Unexpected select-all delete text: {sel32_btn}"
            page.locator("#talonauto-host >> #deleteSelectedBtn").click()
            assert page.locator("#talonauto-host >> #tbody tr").count() == 0
            print("  [OK] DB Test 2 (Tricky CSV + Excel =\"...\" + Bulk Checkboxes & Select-All Delete): passed")

            # --- DB Test 3: Database Search (/admin/tickets?q=<prefix>) ---
            state["export_enabled"] = False
            state["db_pages"] = {}
            state["search_db"] = ["99999600000025240770", "99999600000025240867"]
            res3 = import_pdf_and_get_dups(A95_PDF, 100)
            assert res3["counterText"] == "⚠️ Задубльовані: 2", f"DB Test 3 counter={res3['counterText']}"
            assert res3["dupSerials"] == ["99999600000025240770", "99999600000025240867"], res3["dupSerials"]
            print(f"  [OK] DB Test 3 (DB Search ?q= on 100 A-95 PDF): {res3['counterText']}")

            # --- DB Test 4: Re-import DP_PDF after uploading all 37 coupons to DB -> 37/37 red ---
            state["submissions"].clear()
            state["export_enabled"] = True
            state["export_csv"] = "ID;Номер талона;Пальне\n"
            state["db_pages"] = {}
            state["search_db"] = []
            state["record_to_db"] = True

            res4_before = import_pdf_and_get_dups(DP_PDF, 37)
            assert res4_before["counterText"] == "✓ Задубльовані: 0", res4_before["counterText"]
            page.locator("#talonauto-host >> #uploadBtn").click()
            page.wait_for_function(
                """() => {
                    const sr = document.getElementById('talonauto-host')?.shadowRoot;
                    return sr && sr.getElementById('statusText')?.textContent.includes('Готово! Додано: 37, помилок: 0');
                }""",
                timeout=30_000,
            )
            assert len(state["submissions"]) == 37

            res4_after = import_pdf_and_get_dups(DP_PDF, 37)
            assert res4_after["counterText"] == "⚠️ Задубльовані: 37", f"DB Test 4 counter={res4_after['counterText']}"
            assert len(res4_after["dupSerials"]) == 37
            print(f"  [OK] DB Test 4 (Re-import after upload): all 37/37 flagged red ({res4_after['counterText']})")

            assert not console_errors, f"Browser page errors detected: {console_errors}"
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    run_python_parser_tests()
    run_extension_e2e_tests()
    print("ALL LAB TESTS PASSED (37 DP + 100 A-95)")
