import base64
import io
import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

import pymupdf as fitz
from PIL import Image


@dataclass
class ParsedCoupon:
    index: int
    page: int
    fuel_type: str
    azs: str
    nominal: str
    expires_at: str  # YYYY-MM-DD for <input type="date">
    quantity: int
    serial_number: str
    note: str
    image_base64: str  # data:image/png;base64,...
    width: int
    height: int


def _dedupe_rects(rects: List[fitz.Rect], iou_threshold: float = 0.6) -> List[fitz.Rect]:
    """Keep outer/distinct rectangles and remove nested or duplicate ones."""
    # Sort largest area first
    sorted_rects = sorted(rects, key=lambda r: r.get_area(), reverse=True)
    kept: List[fitz.Rect] = []
    for r in sorted_rects:
        duplicate = False
        for k in kept:
            inter = r & k
            if inter.is_empty:
                continue
            inter_area = inter.get_area()
            # If r is mostly inside k, skip r
            if inter_area / max(r.get_area(), 1e-6) > iou_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(r)
    return kept


def _find_coupon_rects_vector(page: fitz.Page) -> List[fitz.Rect]:
    """Detect coupon card bounding boxes from PDF vector drawings."""
    pw, ph = page.rect.width, page.rect.height
    candidates: List[fitz.Rect] = []

    for d in page.get_drawings():
        r = d.get("rect")
        if not r:
            continue
        w, h = r.width, r.height
        # Typical coupon card on A4 (e.g., 3x3, 2x4, 2x3): 18%-55% width, 15%-50% height
        if 0.18 * pw <= w <= 0.55 * pw and 0.15 * ph <= h <= 0.50 * ph:
            candidates.append(fitz.Rect(r))

    if not candidates:
        return []

    kept = _dedupe_rects(candidates)
    # Sort top-to-bottom (row-wise with tolerance), then left-to-right
    kept.sort(key=lambda r: (round(r.y0 / 30), r.x0))
    return kept


def _find_coupon_rects_whitespace(page: fitz.Page) -> List[fitz.Rect]:
    """Fallback: render page at low DPI and split by white gutters."""
    scale = 1.5
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
    w, h = img.size
    pixels = img.load()

    def find_segments(is_row: bool, limit_other: int, limit_main: int, min_size: int) -> List[Tuple[int, int]]:
        non_white = []
        for i in range(limit_main):
            has_ink = False
            for j in range(limit_other):
                val = pixels[j, i] if is_row else pixels[i, j]
                if val < 245:
                    has_ink = True
                    break
            non_white.append(has_ink)

        segments = []
        start = None
        gap = 0
        for idx, ink in enumerate(non_white):
            if ink:
                if start is None:
                    start = idx
                gap = 0
            else:
                if start is not None:
                    gap += 1
                    if gap > 8:  # >8 px white gutter ends segment
                        end = idx - gap
                        if end - start >= min_size:
                            segments.append((start, end))
                        start = None
                        gap = 0
        if start is not None:
            end = limit_main - 1
            if end - start >= min_size:
                segments.append((start, end))
        return segments

    rows = find_segments(True, w, h, min_size=int(0.12 * h))
    rects: List[fitz.Rect] = []
    for y0, y1 in rows:
        # Find column segments within this row band
        col_ink = []
        for x in range(w):
            has_ink = False
            for y in range(y0, y1 + 1):
                if pixels[x, y] < 245:
                    has_ink = True
                    break
            col_ink.append(has_ink)

        start = None
        gap = 0
        for x, ink in enumerate(col_ink):
            if ink:
                if start is None:
                    start = x
                gap = 0
            else:
                if start is not None:
                    gap += 1
                    if gap > 8:
                        end = x - gap
                        if end - start >= int(0.15 * w):
                            rects.append(fitz.Rect(start / scale, y0 / scale, end / scale, y1 / scale))
                        start = None
                        gap = 0
        if start is not None:
            end = w - 1
            if end - start >= int(0.15 * w):
                rects.append(fitz.Rect(start / scale, y0 / scale, end / scale, y1 / scale))

    return rects


def _extract_fields(text: str) -> dict:
    """Parse fuel_type, azs, nominal, expires_at, serial_number from coupon text."""
    clean = text.replace("\xa0", " ")
    upper = clean.upper()

    # 1. AZS
    azs = ""
    if "ОККО" in upper or "OKKO" in upper:
        azs = "ОККО"
    elif "WOG" in upper or "ВОГ" in upper:
        azs = "WOG"
    elif "УКРНАФТА" in upper or "UKRNAFTA" in upper:
        azs = "УКРНАФТА"

    # 2. Fuel type
    fuel_type = ""
    if re.search(r"\b(?:ДП|ДИЗЕЛЬ|DIESEL)\b", upper):
        fuel_type = "ДП"
    elif re.search(r"(?:А-?95|A-?95|PULLS\s*95)", upper):
        fuel_type = "А-95"
    elif re.search(r"(?:А-?92|A-?92)", upper):
        fuel_type = "А-92"
    elif re.search(r"\b(?:ГАЗ|LPG)\b", upper):
        fuel_type = "Газ"

    # 3. Nominal (e.g. "10 л", "20 л")
    nominal = ""
    m_nom = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:л|l|літр)\b", clean, re.IGNORECASE)
    if m_nom:
        nominal = m_nom.group(1).replace(",", ".")

    # 4. Expiry date -> YYYY-MM-DD
    expires_at = ""
    m_exp = re.search(
        r"(?:дійсний\s+до|термін\s+(?:дії|придатності)|придатний\s+до|до)\s*[:\-]?\s*(\d{2})\.(\d{2})\.(\d{4})",
        clean,
        re.IGNORECASE,
    )
    if not m_exp:
        m_exp = re.search(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", clean)
    if m_exp:
        dd, mm, yyyy = m_exp.groups()
        expires_at = f"{yyyy}-{mm}-{dd}"

    # 5. Serial number (long digit sequence on its own line or >= 8 digits)
    serial_number = ""
    for line in clean.splitlines():
        s = line.strip()
        if re.fullmatch(r"\d{6,28}", s):
            serial_number = s
            break
    if not serial_number:
        # Fallback: any 10-28 digit sequence
        m_ser = re.search(r"\b(\d{10,28})\b", clean)
        if m_ser:
            serial_number = m_ser.group(1)

    return {
        "azs": azs,
        "fuel_type": fuel_type,
        "nominal": nominal,
        "expires_at": expires_at,
        "serial_number": serial_number,
    }


def _detect_banner_fuel_type(img: Image.Image) -> str:
    """Detect OKKO fuel type from top banner color when text layer omits it."""
    banner = img.crop((0, 0, img.width, max(1, int(img.height * 0.45))))
    # Downsample slightly for fast pixel scan
    banner.thumbnail((160, 160))
    pixels = banner.getdata()
    total = len(pixels)
    if total == 0:
        return ""

    yellow = 0
    cyan_blue = 0
    for r, g, b in pixels:
        if r > 200 and g > 180 and b < 70:
            yellow += 1
        elif b > 175 and g > 110 and r < 70:
            cyan_blue += 1

    threshold = total * 0.02
    if yellow > threshold and yellow >= cyan_blue:
        return "ДП"
    if cyan_blue > threshold and cyan_blue > yellow:
        return "А-95"
    return ""


def _render_crop_base64(page: fitz.Page, rect: fitz.Rect, min_longest_px: int = 950) -> Tuple[str, int, int, str]:
    """Render cropped coupon rect to high-res PNG base64 data URI and detect banner fuel color."""
    padded = fitz.Rect(
        max(0, rect.x0 - 3),
        max(0, rect.y0 - 3),
        min(page.rect.width, rect.x1 + 3),
        min(page.rect.height, rect.y1 + 3),
    )
    longest_pt = max(padded.width, padded.height, 1.0)
    scale = max(3.0, min_longest_px / longest_pt)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=padded, alpha=False)

    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    banner_fuel = _detect_banner_fuel_type(img)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}", pix.width, pix.height, banner_fuel


def parse_pdf_coupons(pdf_bytes: bytes, default_fuel_type: str = "") -> List[dict]:
    """Slice all coupons from a PDF and extract their metadata + screenshots."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    coupons: List[ParsedCoupon] = []
    idx = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        rects = _find_coupon_rects_vector(page)
        if not rects:
            rects = _find_coupon_rects_whitespace(page)

        for rect in rects:
            # Expand clip slightly to ensure all text inside border is captured
            text_clip = fitz.Rect(
                max(0, rect.x0 - 2),
                max(0, rect.y0 - 2),
                min(page.rect.width, rect.x1 + 2),
                min(page.rect.height, rect.y1 + 2),
            )
            text = page.get_text("text", clip=text_clip)
            fields = _extract_fields(text)

            # Skip empty boxes that have neither serial nor nominal
            if not fields["serial_number"] and not fields["nominal"]:
                continue

            idx += 1
            img_b64, w, h, banner_fuel = _render_crop_base64(page, rect)
            coupons.append(
                ParsedCoupon(
                    index=idx,
                    page=page_num + 1,
                    fuel_type=default_fuel_type or fields["fuel_type"] or banner_fuel,
                    azs=fields["azs"],
                    nominal=fields["nominal"],
                    expires_at=fields["expires_at"],
                    quantity=1,
                    serial_number=fields["serial_number"],
                    note="",
                    image_base64=img_b64,
                    width=w,
                    height=h,
                )
            )

    doc.close()
    return [asdict(c) for c in coupons]
