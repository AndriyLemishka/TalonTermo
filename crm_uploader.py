import time
from pathlib import Path
from typing import Callable, List, Optional

from playwright.sync_api import sync_playwright, Page


CRM_URL = "https://driver.tun.com.ua/admin/tickets"
PROFILE_DIR = Path(__file__).parent / ".chrome_profile"


def _launch_context(playwright):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for channel in ("chrome", "msedge", None):
        try:
            kwargs = {
                "user_data_dir": str(PROFILE_DIR),
                "headless": False,
                "viewport": {"width": 1280, "height": 860},
            }
            if channel:
                kwargs["channel"] = channel
            return playwright.chromium.launch_persistent_context(**kwargs)
        except Exception:
            continue
    raise RuntimeError(
        "Не вдалося запустити Chrome/Edge. Перевірте, що встановлено Google Chrome або Microsoft Edge."
    )


def _attach_photo(page: Page, image_base64: str, filename: str) -> None:
    """Attach base64 PNG image using the CRM's native _termoUnionPaste handler (with hidden-input fallback)."""
    page.evaluate(
        """async ({ dataUrl, filename }) => {
            const field = document.querySelector('[data-upload]');
            const hidden = document.querySelector('input[name="photo_data"]');
            if (field && typeof field._termoUnionPaste === 'function') {
                const res = await fetch(dataUrl);
                const blob = await res.blob();
                const file = new File([blob], filename, { type: blob.type || 'image/png' });
                field._termoUnionPaste(file);
                // Wait briefly for FileReader inside _termoUnionPaste to finish populating hidden input
                for (let i = 0; i < 30; i++) {
                    if (hidden && hidden.value && hidden.value.startsWith('data:image/')) {
                        return;
                    }
                    await new Promise(r => setTimeout(r, 50));
                }
            }
            if (hidden) {
                hidden.value = dataUrl;
            }
        }""",
        {"dataUrl": image_base64, "filename": filename},
    )


def upload_coupons_to_crm(
    coupons: List[dict],
    on_progress: Optional[Callable[[dict], None]] = None,
    dry_run: bool = False,
) -> dict:
    """
    Open TermoUnion CRM in Chrome, wait for login if needed, and submit all coupons one by one.
    If dry_run=True, fills only the first coupon without clicking submit (for verification).
    """
    results = {"total": len(coupons), "uploaded": 0, "failed": 0, "errors": []}

    def emit(event: dict):
        if on_progress:
            on_progress(event)

    with sync_playwright() as p:
        context = _launch_context(p)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            emit({"status": "opening", "message": "Відкриваю CRM..."})
            page.goto(CRM_URL, wait_until="domcontentloaded")

            # Wait for #fuel_type to appear (user may need to log in first)
            if page.locator("#fuel_type").count() == 0:
                emit({
                    "status": "login_required",
                    "message": "Увійдіть у CRM у відкритому вікні браузера (очікую до 3 хвилин)...",
                })
                page.wait_for_selector("#fuel_type", timeout=180_000)

            for i, coupon in enumerate(coupons, start=1):
                serial = coupon.get("serial_number", f"#{i}")
                emit({
                    "status": "uploading",
                    "current": i,
                    "total": len(coupons),
                    "serial": serial,
                    "message": f"Заповнюю талон {i}/{len(coupons)} ({serial})...",
                })

                try:
                    # Make sure add panel is open
                    page.locator("details.add-panel").evaluate("el => { el.open = true; }")

                    page.select_option("#fuel_type", coupon["fuel_type"])
                    page.select_option("#azs", coupon["azs"])
                    page.fill("#nominal", str(coupon["nominal"]))
                    page.fill("#expires_at", coupon["expires_at"])
                    page.fill("#quantity", str(coupon.get("quantity", 1)))
                    page.fill("#serial_number", serial)
                    page.fill("#note", coupon.get("note", ""))

                    if coupon.get("image_base64"):
                        _attach_photo(page, coupon["image_base64"], f"talon_{serial}.png")

                    if dry_run:
                        emit({
                            "status": "done",
                            "message": "Тестове заповнення першого талона завершено (кнопка 'Додати' не натискалась).",
                        })
                        time.sleep(5)
                        break

                    with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
                        page.click('form[action$="/admin/tickets"] button[type="submit"]')

                    results["uploaded"] += 1
                    emit({
                        "status": "uploaded_one",
                        "current": i,
                        "total": len(coupons),
                        "serial": serial,
                        "message": f"Додано {i}/{len(coupons)}: {serial}",
                    })
                except Exception as exc:
                    results["failed"] += 1
                    err_msg = f"Талон {serial}: {exc}"
                    results["errors"].append(err_msg)
                    emit({
                        "status": "error_one",
                        "current": i,
                        "total": len(coupons),
                        "serial": serial,
                        "message": err_msg,
                    })
                    # Reload tickets page to recover form state for next coupon
                    try:
                        page.goto(CRM_URL, wait_until="domcontentloaded")
                    except Exception:
                        pass

            emit({
                "status": "done",
                "uploaded": results["uploaded"],
                "failed": results["failed"],
                "errors": results["errors"],
                "message": f"Готово! Додано: {results['uploaded']}, помилок: {results['failed']}.",
            })
        finally:
            context.close()

    return results
