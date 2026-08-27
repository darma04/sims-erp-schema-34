"""
==========================================================================
 WEB PROJECT VIEWS - Custom Error Handlers & System View
==========================================================================
 File ini menangani halaman error kustom:

 - custom_error_404() → Halaman "Tidak Ditemukan" (404)
 - custom_error_403() → Halaman "Tidak Punya Akses" (403)
 - custom_error_400() → Halaman "Bad Request" (400)
 - custom_error_500() → Halaman "Server Error" (500)
 - custom_error_401() → Halaman "Tidak Terotentikasi" (401)
 - SystemView        → View generik untuk halaman sistem

 Semua error handler menggunakan layout_blank.html (tanpa sidebar).
 Didaftarkan di config/urls.py: handler404, handler403, handler400, handler500, handler401

 Terhubung dengan:
 - config/urls.py → Registrasi error handler
 - templates → Template halaman error
==========================================================================
"""
from django.views.generic import TemplateView
from django.shortcuts import render
from web_project import TemplateLayout
from web_project.template_helpers.theme import TemplateHelper


class SystemView(TemplateView):
    template_name = "pages/system/not-found.html"
    status = ""

    def get_context_data(self, **kwargs):
        # A function to init the global layout. It is defined in web_project/__init__.py file
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        # Define the layout for this module
        # _templates/layout/system.html
        context.update(
            {
                "layout_path": TemplateHelper.set_layout("system.html", context),
                "status": self.status,
            }
        )

        return context


# Custom Error Handlers
def custom_error_404(request, exception):
    """Handler untuk error 404 - Page Not Found"""
    context = {
        "layout_path": "layout/layout_blank.html",
        "status": 404,
        "style": request.COOKIES.get("style", "light"),
    }
    return render(request, "pages_misc_error.html", context, status=404)


def custom_error_403(request, exception):
    """Handler untuk error 403 - Forbidden"""
    context = {
        "layout_path": "layout/layout_blank.html",
        "status": 403,
        "style": request.COOKIES.get("style", "light"),
    }
    return render(request, "pages_misc_not_authorized.html", context, status=403)


def custom_error_400(request, exception):
    """Handler untuk error 400 - Bad Request"""
    context = {
        "layout_path": "layout/layout_blank.html",
        "status": 400,
        "style": request.COOKIES.get("style", "light"),
    }
    return render(request, "pages_misc_error.html", context, status=400)


def custom_error_500(request):
    """Handler untuk error 500 - Server Error"""
    context = {
        "layout_path": "layout/layout_blank.html",
        "status": 500,
        "style": request.COOKIES.get("style", "light"),
    }
    return render(request, "pages_misc_server_error.html", context, status=500)


def custom_error_401(request, exception=None):
    """Handler untuk error 401 - Unauthorized"""
    context = {
        "layout_path": "layout/layout_blank.html",
        "status": 401,
        "style": request.COOKIES.get("style", "light"),
    }
    return render(request, "errors/401.html", context, status=401)