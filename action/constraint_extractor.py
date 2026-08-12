"""
Vivy AI — Action System: Constraint Extractor
==============================================
Extracts structured constraints from natural language without hardcoding only
the example phrases from the spec. Uses generalised regex + word-to-number
conversion that handles any similar phrasing.

Spec reference: §14 (Budget / Constraint Extraction)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ── Word → Number conversion (handles "one thousand", "five hundred", etc.) ──

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_MULTS = {
    "hundred": 100, "thousand": 1000, "lakh": 100000, "lac": 100000,
    "million": 1000000, "billion": 1000000000,
}


def _words_to_number(text: str) -> Optional[float]:
    """
    Convert an English word-number phrase to a float.
    Examples: "one thousand" → 1000.0, "five hundred" → 500.0, "two lakh" → 200000.0
    Returns None if conversion fails.
    """
    words = text.strip().lower().split()
    current = 0.0
    result = 0.0
    for w in words:
        w = w.strip(".,")
        if w in _ONES:
            current += _ONES[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w in _MULTS:
            mult = _MULTS[w]
            if mult >= 1000:
                result = (result + (current or 1)) * mult if mult >= 1_000_000 else (result + (current or 1)) * mult
                current = 0.0
            else:
                current *= mult
        else:
            # Unknown word — stop here, return partial result if any
            break
    result += current
    return result if result > 0 else None


def _extract_numeric(text: str) -> Optional[float]:
    """
    Extract a numeric value from text — handles digits, commas, ₹ symbol,
    and word-number phrases.
    """
    text = text.strip()
    # Direct numeric (digits + optional commas): "1,000" → 1000
    m = re.search(r"[\d,]+(?:\.\d+)?", text)
    if m:
        try:
            return float(m.group(0).replace(",", ""))
        except ValueError:
            pass
    # Word-number fallback
    return _words_to_number(text)


# ── Currency detection ─────────────────────────────────────────────────────────

_CURRENCY_MAP = {
    "₹": "INR", "rs": "INR", "rs.": "INR", "rupee": "INR", "rupees": "INR", "inr": "INR",
    "$": "USD", "dollar": "USD", "dollars": "USD", "usd": "USD",
    "€": "EUR", "euro": "EUR", "euros": "EUR", "eur": "EUR",
    "£": "GBP", "pound": "GBP", "pounds": "GBP", "gbp": "GBP",
}

def _detect_currency(text: str) -> str:
    text_l = text.lower()
    for symbol, code in _CURRENCY_MAP.items():
        if symbol in text_l:
            return code
    return "INR"  # default for this deployment region


# ── Main extractor ─────────────────────────────────────────────────────────────

class ConstraintExtractor:
    """
    Extracts structured constraints (price, brand, quality, quantity) from
    natural language using generalised patterns.

    Spec reference: §14
    """

    # Budget patterns — ordered from most specific to most general
    _BUDGET_PATTERNS: List[Tuple[str, str, str]] = [
        # (pattern, min_or_max, description)
        (r"between\s+(?:[\₹\$\€\£]?\s*)([\w\s,]+?)\s+(?:and|to|–|-)\s+(?:[\₹\$\€\£]?\s*)([\w\s,]+?)(?:\s|$|,|\.)", "range", "range"),
        (r"(?:from)\s+(?:[\₹\$\€\£]?\s*)([\w\s,]+?)\s+(?:to|upto|up\s+to)\s+(?:[\₹\$\€\£]?\s*)([\w\s,]+?)(?:\s|$|,|\.)", "range", "range"),
        (r"(?:under|below|less\s+than|within|upto|up\s+to|max(?:imum)?|at\s+most)\s+(?:[\₹\$\€\£]?\s*)([\w\s,]+?)(?:\s|$|,|\.)", "max", "below"),
        (r"(?:above|over|more\s+than|at\s+least|min(?:imum)?|starting\s+from)\s+(?:[\₹\$\€\£]?\s*)([\w\s,]+?)(?:\s|$|,|\.)", "min", "above"),
        (r"(?:around|approximately|about|near|roughly)\s+(?:[\₹\$\€\£]?\s*)([\w\s,]+?)(?:\s|$|,|\.)", "approx", "approx"),
        (r"(?:my\s+budget\s+is|budget(?:\s+of)?)\s+(?:[\₹\$\€\£]?\s*)([\w\s,]+?)(?:\s|$|,|\.)", "max", "budget"),
        (r"(?:[\₹\$\€\£]\s*)([\d,]+(?:\.\d+)?)", "max", "currency_symbol"),
    ]

    _QUALITY_KEYWORDS = {
        "cheap": "economy",
        "cheapest": "economy",
        "budget": "economy",
        "affordable": "economy",
        "low cost": "economy",
        "inexpensive": "economy",
        "best": "premium",
        "premium": "premium",
        "high quality": "premium",
        "top rated": "premium",
        "highly rated": "premium",
        "best rated": "premium",
        "good": "mid_range",
        "decent": "mid_range",
    }

    _BRAND_INDICATORS = [
        r"(?:brand(?:\s+is)?|by|from|made\s+by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:brand|products?|speakers?|phones?|laptops?)",
    ]

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Parse all constraints from a natural language string.

        Returns:
            {
                "min_price":    float | None,
                "max_price":    float | None,
                "approx_price": float | None,
                "currency":     str,
                "quality_pref": str | None,   # "economy" | "mid_range" | "premium"
                "brand_pref":   str | None,
                "quantity":     int | None,
                "raw":          str,
                "has_budget":   bool,
            }
        """
        result: Dict[str, Any] = {
            "min_price":    None,
            "max_price":    None,
            "approx_price": None,
            "currency":     _detect_currency(text),
            "quality_pref": None,
            "brand_pref":   None,
            "quantity":     None,
            "raw":          text,
            "has_budget":   False,
        }

        text_lower = text.lower()

        # ── Budget extraction ──────────────────────────────────────────────────
        for pattern, kind, _ in self._BUDGET_PATTERNS:
            m = re.search(pattern, text_lower, re.IGNORECASE)
            if m:
                groups = m.groups()
                if kind == "range" and len(groups) >= 2:
                    lo = _extract_numeric(groups[0])
                    hi = _extract_numeric(groups[1])
                    if lo is not None:
                        result["min_price"] = lo
                    if hi is not None:
                        result["max_price"] = hi
                    result["has_budget"] = True
                    break
                elif kind in ("max", "budget") and groups:
                    val = _extract_numeric(groups[0])
                    if val is not None:
                        result["max_price"] = val
                        result["has_budget"] = True
                        break
                elif kind == "min" and groups:
                    val = _extract_numeric(groups[0])
                    if val is not None:
                        result["min_price"] = val
                        result["has_budget"] = True
                        break
                elif kind == "approx" and groups:
                    val = _extract_numeric(groups[0])
                    if val is not None:
                        result["approx_price"] = val
                        # Set a ±20% band as implicit min/max
                        result["min_price"] = val * 0.80
                        result["max_price"] = val * 1.20
                        result["has_budget"] = True
                        break

        # ── Quality preference ─────────────────────────────────────────────────
        for kw, pref in self._QUALITY_KEYWORDS.items():
            if kw in text_lower:
                result["quality_pref"] = pref
                break

        # ── Brand preference (capital-letter brand names) ──────────────────────
        for bp in self._BRAND_INDICATORS:
            m = re.search(bp, text, re.IGNORECASE)
            if m:
                result["brand_pref"] = m.group(1).strip()
                break

        # ── Quantity ───────────────────────────────────────────────────────────
        qty_m = re.search(r"\b(\d+)\s+(?:pieces?|units?|items?|sets?)\b", text_lower)
        if qty_m:
            try:
                result["quantity"] = int(qty_m.group(1))
            except ValueError:
                pass

        return result

    def apply_to_candidates(
        self,
        candidates: List[Dict[str, Any]],
        constraints: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Filter and rank a candidate list based on extracted constraints.
        Only removes a candidate if it definitely violates a constraint.
        Spec reference: §12 (apply budget filter), §14
        """
        if not candidates or not constraints.get("has_budget"):
            return candidates

        min_p  = constraints.get("min_price")
        max_p  = constraints.get("max_price")
        brand  = (constraints.get("brand_pref") or "").lower()
        qual   = constraints.get("quality_pref")

        filtered = []
        for c in candidates:
            price_str = str(c.get("price", "")).lower()
            price_val = _extract_numeric(price_str)

            passes = True
            if price_val is not None:
                if min_p is not None and price_val < min_p:
                    passes = False
                if max_p is not None and price_val > max_p:
                    passes = False

            if passes and brand:
                label = str(c.get("label", "")).lower()
                if brand not in label:
                    # Don't hard-exclude by brand — just deprioritise
                    c = dict(c)
                    c["_brand_match"] = False
                else:
                    c = dict(c)
                    c["_brand_match"] = True

            if passes:
                filtered.append(c)

        # Sort: brand matches first, then by price ascending (if available)
        def _sort_key(c: Dict[str, Any]) -> Tuple:
            brand_ok = 0 if c.get("_brand_match") else 1
            pv = _extract_numeric(str(c.get("price", ""))) or 999999
            return (brand_ok, pv)

        return sorted(filtered, key=_sort_key)


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[ConstraintExtractor] = None


def get_constraint_extractor() -> ConstraintExtractor:
    global _instance
    if _instance is None:
        _instance = ConstraintExtractor()
    return _instance
