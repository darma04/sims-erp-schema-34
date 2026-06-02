"""
==========================================================================
 CURRENCY FILTERS - Template Filter Format Angka & Mata Uang
==========================================================================
 Custom template filters untuk memformat angka di template HTML:

 Filter:
 - {{ value|rupiah }}              → Rp 1,000,000
 - {{ json_string|json_load_safe }}→ Parse JSON string ke dict
 - {{ value|replace_underscore:' '}}→ Ganti underscore dengan spasi

 Deprecated (tetap dipertahankan untuk backward compatibility):
 - {{ value|format_k }} → alias dari rupiah
 - {{ value|rupiah_k }} → alias dari rupiah

 Cara pakai di template:
 1. {% load currency_filters %}
 2. {{ produk.harga_jual|rupiah }}  → "Rp 500,000"
==========================================================================
"""
from django import template

register = template.Library()  # Registry template filter

@register.filter
def rupiah(value):
    """Format angka menjadi Rupiah dengan koma sebagai pemisah ribuan
    
    Contoh:
    - 1000 -> Rp 1,000
    - 500000 -> Rp 500,000
    - 2500000 -> Rp 2,500,000
    """
    try:
        value = float(value)
        # Format dengan koma sebagai pemisah ribuan
        formatted = f"{value:,.0f}"
        return f"Rp {formatted}"
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
