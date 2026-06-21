"""
Management command untuk minifikasi file CSS dan JS static.

Menghapus komentar dan whitespace berlebih dari file CSS/JS
sehingga komentar tidak muncul di browser saat inspect element,
sekaligus mengurangi ukuran file untuk performa lebih baik.

Cara pakai:
    python manage.py minify_static
    python manage.py minify_static --dry-run
"""

import os
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Minifikasi file CSS dan JS static untuk production"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview tanpa mengubah file",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        static_dirs = self._get_static_dirs()

        if not static_dirs:
            self.stdout.write(self.style.WARNING(
                "Tidak ada static directory ditemukan."
            ))
            return

        total_css = 0
        total_js = 0
        total_saved = 0

        for static_dir in static_dirs:
            css, js, saved = self._minify_dir(static_dir, dry_run)
            total_css += css
            total_js += js
            total_saved += saved

        action = "Preview" if dry_run else "Minified"
        self.stdout.write(self.style.SUCCESS(
            f"\n{action}: {total_css} CSS + {total_js} JS files"
        ))
        if total_saved > 0:
            self.stdout.write(f"Space saved: {total_saved / 1024:.1f} KB")

    def _get_static_dirs(self):
        dirs = set()
        if settings.STATIC_ROOT and os.path.isdir(settings.STATIC_ROOT):
            dirs.add(Path(settings.STATIC_ROOT))
        for d in getattr(settings, "STATICFILES_DIRS", []):
            if isinstance(d, (list, tuple)):
                d = d[1]
            if os.path.isdir(str(d)):
                dirs.add(Path(str(d)))
        return list(dirs)

    def _minify_dir(self, directory, dry_run):
        skip_dirs = {"vendor", "libs", "lib", "node_modules"}
        skip_patterns = {
            "jquery", "bootstrap", "datatables", "select2",
            "chart.js", "apexcharts", "flatpickr", "sweetalert",
            "pdfmake", "jsbarcode", "moment", "perfect-scrollbar",
            "waves", "hammer", "remixicon",
        }

        css_count = 0
        js_count = 0
        total_saved = 0

        for root, dirs, files in os.walk(directory):
            # Skip vendor directories
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for fname in files:
                if fname.endswith(".min.css") or fname.endswith(".min.js"):
                    continue

                fpath = Path(root) / fname
                path_lower = str(fpath).lower()

                if any(p in path_lower for p in skip_patterns):
                    continue

                if fpath.stat().st_size > 500 * 1024:
                    continue

                try:
                    original = fpath.read_text(encoding="utf-8")
                except (UnicodeDecodeError, PermissionError):
                    continue

                if fname.endswith(".css"):
                    minified = self._minify_css(original)
                    css_count += 1
                elif fname.endswith(".js"):
                    minified = self._minify_js(original)
                    js_count += 1
                else:
                    continue

                saved = len(original) - len(minified)
                total_saved += max(0, saved)

                if not dry_run and minified != original:
                    if fname.endswith(".css"):
                        min_path = fpath.with_suffix(".min.css")
                    else:
                        min_path = fpath.with_suffix(".min.js")
                    min_path.write_text(minified, encoding="utf-8")

        return css_count, js_count, total_saved

    def _minify_css(self, content):
        """Remove comments and excessive whitespace from CSS."""
        content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
        content = re.sub(r"\s+", " ", content)
        content = re.sub(r"\s*([{}:;,>~+])\s*", r"\1", content)
        content = content.replace(";}", "}")
        return content.strip()

    def _minify_js(self, content):
        """Remove comments and excessive whitespace from JS (safe approach)."""
        content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
        content = re.sub(r"(?<![:\'\"])\/\/[^\n]*", "", content)
        content = re.sub(r"\n\s*\n", "\n", content)
        content = re.sub(r"^\s+", "", content, flags=re.MULTILINE)
        return content.strip()
