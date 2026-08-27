"""
==========================================================================
 CURRENCY FILTERS - Template Filter Format Angka & Mata Uang
==========================================================================
 Custom template filters untuk memformat angka di template HTML:

 Filter:
 - {{ value|rupiah }}              → Rp 1.000.000
 - {{ value|thousands }}           → 1.000.000 (tanpa prefix Rp)
 - {{ json_string|json_load_safe }}→ Parse JSON string ke dict
 - {{ value|replace_underscore:' '}}→ Ganti underscore dengan spasi

 Deprecated (tetap dipertahankan untuk backward compatibility):
 - {{ value|format_k }} → alias dari rupiah
 - {{ value|rupiah_k }} → alias dari rupiah

 Cara pakai di template:
 1. {% load currency_filters %}
 2. {{ produk.harga_jual|rupiah }}  → "Rp 500.000"
==========================================================================
"""
from django import template

register = template.Library()  # Registry template filter

@register.filter
def rupiah(value):
    """Format angka menjadi Rupiah dengan titik sebagai pemisah ribuan
    (format standar Indonesia).
    
    Contoh:
    - 1000 -> Rp 1.000
    - 500000 -> Rp 500.000
    - 2500000 -> Rp 2.500.000
    - -1500000 -> - Rp 1.500.000
    - -0.5 -> Rp 0
    """
    try:
        value = float(value)
        is_negative = value < 0
        value = abs(value)
        # Format dengan titik sebagai pemisah ribuan
        formatted = f"{value:,.0f}".replace(",", ".")
        # Handle -0: jika hasil rounding adalah "0", selalu tampilkan "Rp 0"
        if formatted == "0":
            return "Rp 0"
        if is_negative:
            return f"- Rp {formatted}"
        return f"Rp {formatted}"
    except (ValueError, TypeError):
        return value


@register.filter
def thousands(value):
    """Format angka dengan titik sebagai pemisah ribuan (tanpa prefix Rp).
    
    Contoh:
    - 1000 -> 1.000
    - 500000 -> 500.000
    - 2500000 -> 2.500.000
    - -1500000 -> - 1.500.000
    - -0.5 -> 0
    """
    try:
        value = float(value)
        is_negative = value < 0
        value = abs(value)
        # Format dengan titik sebagai pemisah ribuan
        formatted = f"{value:,.0f}".replace(",", ".")
        # Handle -0: jika hasil rounding adalah "0", selalu tampilkan "0"
        if formatted == "0":
            return "0"
        if is_negative:
            return f"- {formatted}"
        return formatted
    except (ValueError, TypeError):
        return value


@register.filter
def json_load_safe(value):
    """Memparse JSON string menjadi dictionary secara aman (tidak error jika gagal)"""
    import json
    try:
        if isinstance(value, str):
            return json.loads(value)
        return value
    except Exception:
        return {}


@register.filter
def format_k(value):
    """USANG: Gunakan filter rupiah sebagai pengganti.
    Dipertahankan untuk kompatibilitas mundur.
    """
    return rupiah(value)


@register.filter
def rupiah_k(value):
    """USANG: Gunakan filter rupiah sebagai pengganti.
    Dipertahankan untuk kompatibilitas mundur.
    """
    return rupiah(value)

@register.filter
def replace_underscore(value, arg):
    """Mengganti underscore dengan spasi atau karakter lain"""
    return value.replace("_", arg)

@register.filter
def multiply(value, arg):
    """Mengalikan dua angka (value * arg)"""
    try:
        from decimal import Decimal
        return Decimal(str(value)) * Decimal(str(arg))
    except (ValueError, TypeError, Decimal.InvalidOperation):
        return 0

@register.filter
def subtract(value, arg):
    """Mengurangi dua angka (value - arg)"""
    try:
        from decimal import Decimal
        return Decimal(str(value)) - Decimal(str(arg))
    except (ValueError, TypeError, Decimal.InvalidOperation):
        return 0
