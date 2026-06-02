"""
==========================================================================
 TEMPLATE HELPER - Engine Tema & Layout (Core Framework)
==========================================================================
 Class TemplateHelper adalah inti dari sistem tema aplikasi.
 Bertanggung jawab untuk:

 1. init_context() → Inisialisasi variabel tema dari TEMPLATE_CONFIG
 2. map_context()  → Mapping variabel ke CSS class (navbar, layout, dll)
 3. set_layout()   → Set layout dan load bootstrap class untuk halaman
 4. get_theme_variables() → Ambil variabel tema (nama, versi, dll)
 5. import_class() → Dynamic import module bootstrap per layout

 Alur kerja:
 ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐
 │ config/          │    │ TemplateHelper   │    │ Template     │
 │ template.py      │───→│ init_context()   │───→│ HTML         │
 │ TEMPLATE_CONFIG  │    │ map_context()    │    │ (rendering)  │
 └─────────────────┘    └─────────────────┘    └──────────────┘

 Terhubung dengan:
 - config/template.py → TEMPLATE_CONFIG, THEME_VARIABLES, THEME_LAYOUT_DIR
 - web_project/__init__.py → TemplateLayout yang memanggil TemplateHelper
 - templates/layout/ → File layout HTML yang di-set oleh set_layout()
==========================================================================
"""

from django.conf import settings  # Mengakses konfigurasi Django (termasuk TEMPLATE_CONFIG)
from pprint import pprint          # Pretty print — untuk debug output yang rapi di terminal
import os                          # Modul OS — operasi file dan path
from importlib import import_module, util  # Dynamic import — memuat module Python secara programatis


# ╔══════════════════════════════════════════════════════════════╗
# ║                CLASS TEMPLATEHELPER                          ║
# ╚══════════════════════════════════════════════════════════════╝
#
# Class utama yang mengelola seluruh konfigurasi tema template.
# Semua method-nya bersifat STATIC (tanpa 'self') — bisa dipanggil
# langsung tanpa membuat instance: TemplateHelper.init_context()
#
class TemplateHelper:

    # ──────────────────────────────────────────────────────────
    # INIT CONTEXT — Inisialisasi Variabel Tema
    # ──────────────────────────────────────────────────────────
    # Menyalin SEMUA nilai dari TEMPLATE_CONFIG (config/template.py)
    # ke dalam context dictionary yang akan dikirim ke template HTML.
    #
    # Parameter:
    #   context (dict) — Dictionary context dari Django view
    #
    # Return:
    #   context (dict) — Dictionary yang sudah ditambah variabel tema
    #
    # Contoh penggunaan di views.py:
    #   context = TemplateHelper.init_context(context)
    #   # Sekarang context punya key: 'layout', 'theme', 'style', dll
    # ──────────────────────────────────────────────────────────
    def init_context(context):
        context.update(
            {
                # Tipe layout: "vertical" atau "horizontal"
                "layout": settings.TEMPLATE_CONFIG.get("layout"),

                # Tema warna: "theme-default", "theme-bordered", "theme-semi-dark"
                "theme": settings.TEMPLATE_CONFIG.get("theme"),

                # Gaya warna: "light", "dark", atau "system"
                "style": settings.TEMPLATE_CONFIG.get("style"),

                # Dukungan RTL (Right-to-Left): True/False
                "rtl_support": settings.TEMPLATE_CONFIG.get("rtl_support"),

                # Mode RTL aktif: True/False
                "rtl_mode": settings.TEMPLATE_CONFIG.get("rtl_mode"),

                # Apakah file JS customizer dimuat: True/False
                "has_customizer": settings.TEMPLATE_CONFIG.get("has_customizer"),

                # Apakah UI customizer ditampilkan: True/False
                "display_customizer": settings.TEMPLATE_CONFIG.get(
                    "display_customizer"
                ),

                # Lebar konten: "compact" (container-xxl) atau "wide" (container-fluid)
                "content_layout": settings.TEMPLATE_CONFIG.get("content_layout"),

                # Tipe navbar: "fixed", "static", atau "hidden"
                "navbar_type": settings.TEMPLATE_CONFIG.get("navbar_type"),

                # Tipe header (layout horizontal): "fixed" atau "static"
                "header_type": settings.TEMPLATE_CONFIG.get("header_type"),

                # Apakah menu sidebar fixed saat scroll: True/False
                "menu_fixed": settings.TEMPLATE_CONFIG.get("menu_fixed"),

                # Apakah menu sidebar dalam keadaan collapse: True/False
                "menu_collapsed": settings.TEMPLATE_CONFIG.get("menu_collapsed"),

                # Apakah footer fixed di bawah layar: True/False
                "footer_fixed": settings.TEMPLATE_CONFIG.get("footer_fixed"),

                # Dropdown terbuka saat hover (layout horizontal): True/False
                "show_dropdown_onhover": settings.TEMPLATE_CONFIG.get(
                    "show_dropdown_onhover"
                ),

                # Daftar kontrol yang ditampilkan di panel customizer
                "customizer_controls": settings.TEMPLATE_CONFIG.get(
                    "customizer_controls"
                ),
            }
        )
        return context

    # ──────────────────────────────────────────────────────────
    # MAP CONTEXT — Konversi Nilai Config ke CSS Class
    # ──────────────────────────────────────────────────────────
    # Mengambil nilai konfigurasi dari context dan mengkonversinya
    # menjadi CSS class yang digunakan oleh template HTML.
    #
    # Contoh konversi:
    #   navbar_type="fixed"  → navbar_type_class="layout-navbar-fixed"
    #   menu_collapsed=True  → menu_collapsed_class="layout-menu-collapsed"
    #   content_layout="wide" → container_class="container-fluid"
    #
    # Parameter:
    #   context (dict) — Dictionary context yang sudah diisi init_context()
    #
    # Tidak ada return — langsung memodifikasi context dictionary (mutable)
    # ──────────────────────────────────────────────────────────
    def map_context(context):

        # ─── HEADER TYPE (khusus layout horizontal) ───
        # Menentukan CSS class untuk header di layout horizontal
        # "fixed"  → "layout-menu-fixed" (header tetap di atas saat scroll)
        # "static" → "" (header ikut scroll)
        if context.get("layout") == "horizontal":
            if context.get("header_type") == "fixed":
                context["header_type_class"] = "layout-menu-fixed"
            elif context.get("header_type") == "static":
                context["header_type_class"] = ""
            else:
                context["header_type_class"] = ""
        else:
            # Layout vertical tidak menggunakan header_type
            context["header_type_class"] = ""

        # ─── NAVBAR TYPE (khusus layout vertical) ───
        # Menentukan CSS class untuk navbar (menu atas) di layout vertical
        # "fixed"  → "layout-navbar-fixed" (navbar tetap saat scroll)
        # "static" → "" (navbar ikut scroll)
        # "hidden" → "layout-navbar-hidden" (navbar disembunyikan)
        if context.get("layout") != "horizontal":
            if context.get("navbar_type") == "fixed":
                context["navbar_type_class"] = "layout-navbar-fixed"
            elif context.get("navbar_type") == "static":
                context["navbar_type_class"] = ""
            else:
                context["navbar_type_class"] = "layout-navbar-hidden"
        else:
            # Layout horizontal tidak menggunakan navbar_type
            context["navbar_type_class"] = ""

        # ─── MENU COLLAPSED (sidebar collapse) ───
        # Jika True → sidebar dalam keadaan sempit (hanya ikon)
        # CSS class "layout-menu-collapsed" mengaktifkan animasi collapse
        context["menu_collapsed_class"] = (
            "layout-menu-collapsed" if context.get("menu_collapsed") else ""
        )

        # ─── MENU FIXED (khusus layout vertical) ───
        # Jika True → sidebar tetap di posisi saat halaman di-scroll
        # CSS class "layout-menu-fixed" membuat sidebar position:fixed
        if context.get("layout") == "vertical":
            if context.get("menu_fixed") is True:
                context["menu_fixed_class"] = "layout-menu-fixed"
            else:
                context["menu_fixed_class"] = ""

        # ─── FOOTER FIXED ───
        # Jika True → footer selalu terlihat di bawah layar
        # CSS class "layout-footer-fixed" membuat footer position:fixed
        context["footer_fixed_class"] = (
            "layout-footer-fixed" if context.get("footer_fixed") else ""
        )

        # ─── RTL SUPPORT ───
        # Jika True → path "/rtl" ditambahkan ke URL asset CSS
        # Digunakan untuk memuat file CSS versi RTL (Right-to-Left)
        context["rtl_support_value"] = "/rtl" if context.get("rtl_support") else ""

        # ─── RTL MODE ───
        # Menentukan arah teks dan layout halaman
        # True  → dir="rtl" (teks dari kanan ke kiri, untuk bahasa Arab/Ibrani)
        # False → dir="ltr" (teks dari kiri ke kanan, untuk bahasa Latin/Indonesia)
        context["rtl_mode_value"], context["text_direction_value"] = (
            ("rtl", "rtl") if context.get("rtl_mode") else ("ltr", "ltr")
        )

        # ─── SHOW DROPDOWN ON HOVER (layout horizontal) ───
        # Menghasilkan string "true"/"false" untuk atribut data-*
        # Digunakan oleh JavaScript untuk mengontrol perilaku dropdown
        context["show_dropdown_onhover_value"] = (
            "true" if context.get("show_dropdown_onhover") else "false"
        )

        # ─── DISPLAY CUSTOMIZER ───
        # Mengontrol visibilitas panel customizer di UI
        # True  → "" (customizer terlihat)
        # False → "customizer-hide" (customizer disembunyikan via CSS)
        context["display_customizer_class"] = (
            "" if context.get("display_customizer") else "customizer-hide"
        )

        # ─── CONTENT LAYOUT (lebar konten) ───
        # Menentukan lebar area konten utama
        # "wide"    → "container-fluid" (lebar 100% layar)
        # "compact" → "container-xxl" (lebar dibatasi ~1400px)
        if context.get("content_layout") == "wide":
            context["container_class"] = "container-fluid"
            context["content_layout_class"] = "layout-wide"
        else:
            context["container_class"] = "container-xxl"
            context["content_layout_class"] = "layout-compact"

        # ─── DETACHED NAVBAR ───
        # Navbar terpisah dari sidebar (efek visual "mengambang")
        # True  → "navbar-detached" (navbar tidak menempel ke sidebar)
        # False → "" (navbar menempel ke sidebar seperti biasa)
        if context.get("navbar_detached") == True:
            context["navbar_detached_class"] = "navbar-detached"
        else:
            context["navbar_detached_class"] = ""

    # ──────────────────────────────────────────────────────────
    # GET THEME VARIABLES — Ambil Variabel Tema dari Config
    # ──────────────────────────────────────────────────────────
    # Mengambil satu nilai dari THEME_VARIABLES berdasarkan key.
    #
    # Parameter:
    #   scope (str) — Key yang ingin diambil (misal: "template_name")
    #
    # Return:
    #   Nilai dari THEME_VARIABLES[scope]
    #
    # Contoh:
    #   nama_app = TemplateHelper.get_theme_variables("template_name")
    #   # Hasilnya: "SERPTECH"
    # ──────────────────────────────────────────────────────────
    def get_theme_variables(scope):
        return settings.THEME_VARIABLES[scope]

    # ──────────────────────────────────────────────────────────
    # GET THEME CONFIG — Ambil Konfigurasi Tema dari Config
    # ──────────────────────────────────────────────────────────
    # Mengambil satu nilai dari TEMPLATE_CONFIG berdasarkan key.
    #
    # Parameter:
    #   scope (str) — Key yang ingin diambil (misal: "layout")
    #
    # Return:
    #   Nilai dari TEMPLATE_CONFIG[scope]
    #
    # Contoh:
    #   layout = TemplateHelper.get_theme_config("layout")
    #   # Hasilnya: "vertical"
    # ──────────────────────────────────────────────────────────
    def get_theme_config(scope):
        return settings.TEMPLATE_CONFIG[scope]

    # ──────────────────────────────────────────────────────────
    # SET LAYOUT — Set Layout Halaman & Load Bootstrap File
    # ──────────────────────────────────────────────────────────
    # Menentukan file layout yang digunakan untuk halaman tertentu,
    # dan memuat file bootstrap Python yang sesuai.
    #
    # Alur kerja:
    # 1. Ekstrak nama layout dari path view (contoh: "layout/master.html" → "layout")
    # 2. Cari file bootstrap Python di templates/{layout}/bootstrap/{layout}.py
    # 3. Jika ada → import dan jalankan init() untuk setup context
    # 4. Jika tidak ada → gunakan bootstrap default
    # 5. Return path lengkap ke file layout template
    #
    # Parameter:
    #   view (str) — Path relatif ke file template (contoh: "master.html")
    #   context (dict) — Dictionary context yang akan dimodifikasi
    #
    # Return:
    #   str — Path lengkap ke file template (contoh: "layout/master.html")
    #
    # Contoh:
    #   layout_path = TemplateHelper.set_layout("master.html", context)
    #   # Hasilnya: "layout/master.html"
    #   # Dan context sudah ditambah variabel bootstrap
    # ──────────────────────────────────────────────────────────
    def set_layout(view, context={}):
        # Ekstrak nama layout dari path view
        # Contoh: "master.html" → split("/") → ["master.html"] → [0] = "master"
        # Contoh: "vertical/master.html" → split("/") → ["vertical", "master.html"] → [0] = "vertical"
        layout = os.path.splitext(view)[0].split("/")[0]

        # Bangun path module Python untuk bootstrap layout
        # Contoh: "templates.layout.bootstrap.master"
        module = f"templates.{settings.THEME_LAYOUT_DIR.replace('/', '.')}.bootstrap.{layout}"

        # Cek apakah file bootstrap untuk layout ini ada
        # util.find_spec() → None jika module tidak ditemukan
        if util.find_spec(module) is not None:
            # File bootstrap DITEMUKAN → import dan inisialisasi
            # Import class TemplateBootstrap{Layout} dari module
            # Contoh: TemplateBootstrapMaster dari templates.layout.bootstrap.master
            TemplateBootstrap = TemplateHelper.import_class(
                module, f"TemplateBootstrap{layout.title().replace('_', '')}"
            )
            # Jalankan init() untuk setup context dengan variabel khusus layout
            TemplateBootstrap.init(context)
        else:
            # File bootstrap TIDAK DITEMUKAN → gunakan default
            # Fallback ke: templates.layout.bootstrap.default
            module = f"templates.{settings.THEME_LAYOUT_DIR.replace('/', '.')}.bootstrap.default"

            TemplateBootstrap = TemplateHelper.import_class(
                module, "TemplateBootstrapDefault"
            )
            TemplateBootstrap.init(context)

        # Return path lengkap ke file layout template
        # Contoh: "layout" + "/" + "master.html" = "layout/master.html"
        return f"{settings.THEME_LAYOUT_DIR}/{view}"

    # ──────────────────────────────────────────────────────────
    # IMPORT CLASS — Dynamic Import Module Python
    # ──────────────────────────────────────────────────────────
    # Memuat (import) sebuah class dari module Python secara dinamis.
    # Disebut "dynamic import" karena nama module ditentukan saat runtime
    # (bukan hardcoded di kode).
    #
    # Cara kerja:
    # 1. import_module(fromModule) → import module Python berdasarkan string nama
    # 2. getattr(module, import_className) → ambil class dari module tersebut
    #
    # Parameter:
    #   fromModule (str) — Nama module Python (contoh: "templates.layout.bootstrap.master")
    #   import_className (str) — Nama class yang ingin diambil (contoh: "TemplateBootstrapMaster")
    #
    # Return:
    #   Class object yang diminta
    #
    # Contoh:
    #   cls = TemplateHelper.import_class("templates.layout.bootstrap.master", "TemplateBootstrapMaster")
    #   cls.init(context)  # Panggil init() dari class yang diimport
    # ──────────────────────────────────────────────────────────
    def import_class(fromModule, import_className):
        # Debug: cetak modul dan class yang sedang dimuat ke terminal
        if settings.DEBUG:
            pprint(f"Loading {import_className} from {fromModule}")

        # import_module() → import module secara dinamis berdasarkan string nama
        # Contoh: import_module("templates.layout.bootstrap.master")
        #         sama dengan: from templates.layout.bootstrap import master
        module = import_module(fromModule)

        # getattr() → ambil atribut (class/fungsi) dari module berdasarkan nama
        # Contoh: getattr(module, "TemplateBootstrapMaster")
        #         sama dengan: module.TemplateBootstrapMaster
        return getattr(module, import_className)
