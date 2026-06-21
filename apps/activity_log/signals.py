"""
==========================================================================
 ACTIVITY LOG SIGNALS - Auto-Logging via Django Signals
==========================================================================
 File ini berisi signal handlers yang OTOMATIS mencatat setiap
 perubahan data (create/update/delete) di seluruh model aplikasi.

 Apa itu Django Signals?
 - Signals adalah mekanisme "event" di Django
 - Ketika suatu aksi terjadi (save, delete, login), Django mengirim "signal"
 - Signal handler (receiver) akan dipanggil otomatis
 - Mirip konsep Event Listener / Observer Pattern

 Signals yang digunakan:
 ┌────────────────────┬──────────────────────────────────────────┐
 │ Signal             │ Kapan dipicu?                            │
 ├────────────────────┼──────────────────────────────────────────┤
 │ user_logged_in     │ Setelah user berhasil login              │
 │ user_logged_out    │ Setelah user logout                      │
 │ pre_save           │ SEBELUM model disimpan (capture old state)│
 │ post_save          │ SETELAH model disimpan (log create/update)│
 │ post_delete        │ SETELAH model dihapus (log delete)       │
 └────────────────────┴──────────────────────────────────────────┘

 Delta Tracking (Pelacakan Perubahan):
 1. pre_save → Simpan state lama objek ke instance._old_state
 2. post_save → Bandingkan old_state vs new_state → catat perbedaan
 3. Hasil tersimpan sebagai JSON di field 'changes'

 Fungsi utama:
 - log_user_login/logout → Catat login/logout
 - capture_old_state → pre_save: simpan state lama
 - get_field_diff → Bandingkan old vs new field-by-field
 - log_model_change → post_save: catat create/update + delta
 - log_model_delete → post_delete: catat delete
 - register_signals → Daftarkan signals untuk semua model

 Terhubung dengan:
 - middleware.py → get_current_request() untuk mendapat user aktif
 - apps.py → ready() memanggil register_signals() saat startup
 - models.py → UserActivity sebagai target penyimpanan log
==========================================================================
"""
from django.db.models.signals import pre_save, post_save, post_delete
# Import dari framework Django
from django.contrib.auth.signals import user_logged_in, user_logged_out
# Import dari framework Django
from django.dispatch import receiver
# Import dari framework Django
from django.contrib.auth.models import User
# Import dari modul internal proyek
from .models import UserActivity
import json
# Import dari framework Django
from django.core.serializers.json import DjangoJSONEncoder
import datetime
from decimal import Decimal

import logging

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Mencatat aktivitas login user ke database log"""
    try:
        # Import dari modul internal proyek
        from .middleware import get_current_request
        req = get_current_request() or request
        
        def get_client_ip(req):
            """Mendapatkan IP address client dari request HTTP."""
            x_forwarded_for = req.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                return x_forwarded_for.split(',')[0]
            return req.META.get('REMOTE_ADDR')
        
        UserActivity.objects.create(
            user=user,
            action='login',
            description=f"{user.username} logged in",
            ip_address=get_client_ip(req),
            user_agent=req.META.get('HTTP_USER_AGENT', '')[:500]
        )
    except Exception as e:
        logger.warning("Error tidak terduga: %s", e)


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Mencatat aktivitas logout user ke database log"""
    try:
        if user:
            # Import dari modul internal proyek
            from .middleware import get_current_request
            req = get_current_request() or request
            
            def get_client_ip(req):
                """Mendapatkan IP address client dari request HTTP."""
                x_forwarded_for = req.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    return x_forwarded_for.split(',')[0]
                return req.META.get('REMOTE_ADDR')
            
            UserActivity.objects.create(
                user=user,
                action='logout',
                description=f"{user.username} logged out",
                ip_address=get_client_ip(req),
                user_agent=req.META.get('HTTP_USER_AGENT', '')[:500]
            )
    except Exception as e:
        logger.warning("Error tidak terduga: %s", e)


def get_field_diff(instance, old_instance):
    """Menghitung perbedaan antara state lama dan baru dari instance model"""
    if not old_instance:
        return None
        
    diff = {}
    
    # Field yang diabaikan dari pelacakan perubahan (tidak perlu dicatat)
    skipped_fields = ['diupdate_pada', 'dibuat_pada', 'last_login', 'password', 'dibuat_oleh', 'disetujui_oleh']
    
    for field in instance._meta.fields:
        field_name = field.name
        
        if field_name in skipped_fields:
            continue
            
        # Blok penanganan error — coba jalankan kode di bawah
        try:
            old_val = getattr(old_instance, field_name)
            new_val = getattr(instance, field_name)
            
            # Penanganan perbandingan tipe Decimal (konversi ke float)
            if isinstance(old_val, Decimal):
                old_val = float(old_val)
            if isinstance(new_val, Decimal):
                new_val = float(new_val)
                
            # Penanganan perbandingan tipe date/datetime (konversi ke string)
            if isinstance(old_val, (datetime.date, datetime.datetime)):
                old_val = str(old_val)
            if isinstance(new_val, (datetime.date, datetime.datetime)):
                new_val = str(new_val)
                
            if old_val != new_val:
                # Konversi foreign key ke representasi string jika memungkinkan
                if field.is_relation and old_val is not None and new_val is not None:
                    # Blok penanganan error — coba jalankan kode di bawah
                    try:
                        old_val = str(old_val)
                        new_val = str(new_val)
                    except Exception as e:
                        logger.warning("Error tidak terduga: %s", e)
                        
                diff[field_name] = {'old': old_val, 'new': new_val}
        except Exception:
            continue
            
    return diff


def log_model_change(sender, instance, created, **kwargs):
    """Mencatat aksi create/update model beserta pelacakan perubahan (delta tracking)"""
    try:
        # Skip logging untuk UserActivity sendiri
        if sender == UserActivity:
            return
        
        # Ambil request saat ini dari middleware
        from .middleware import get_current_request
        request = get_current_request()
        
        # Skip jika tidak ada request atau user tidak authenticated
        if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
            return
        
        # Ambil informasi model
        model_name = sender._meta.verbose_name or sender.__name__
        object_repr = str(instance)[:200]
        object_id = instance.pk
        action = 'create' if created else 'update'
        
        # Hitung perubahan/delta antara state lama dan baru
        changes_json = None
        description = f"{request.user.username} {action} {model_name}: {object_repr[:100]}"
        
        if not created and hasattr(instance, '_old_state'):
            changes = get_field_diff(instance, instance._old_state)
            if changes:
                changes_json = json.dumps(changes, cls=DjangoJSONEncoder)
                
                # Buat deskripsi detail perubahan
                change_desc = []
                for field, val in changes.items():
                    change_desc.append(f"{field}: {val['old']} -> {val['new']}")
                
                if change_desc:
                    description = f"Update {model_name}: " + ", ".join(change_desc[:3])
                    if len(change_desc) > 3:
                        description += "..."
        
        def get_client_ip(req):
            """Mendapatkan IP address client dari request HTTP."""
            x_forwarded_for = req.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                return x_forwarded_for.split(',')[0]
            return req.META.get('REMOTE_ADDR')
        
        # Buat log aktivitas ke database
        UserActivity.objects.create(
            user=request.user,
            action=action,
            model_name=str(model_name),
            object_id=str(object_id) if object_id else None,
            object_repr=object_repr,
            description=description,
            changes=changes_json,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
        )
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        # Print debug untuk pengembangan (dinonaktifkan di produksi)
        # print(f"Error logging: {e}") 
        pass


def log_model_delete(sender, instance, **kwargs):
    """Mencatat aksi penghapusan model ke database log"""
    try:
        if sender == UserActivity:
            return
        
        # Import dari modul internal proyek
        from .middleware import get_current_request  
        request = get_current_request()
        
        if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
            return
        
        model_name = sender._meta.verbose_name or sender.__name__
        object_repr = str(instance)[:200]
        object_id = instance.pk
        
        def get_client_ip(req):
            """Mendapatkan IP address client dari request HTTP."""
            x_forwarded_for = req.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                return x_forwarded_for.split(',')[0]
            return req.META.get('REMOTE_ADDR')
        
        UserActivity.objects.create(
            user=request.user,
            action='delete',
            model_name=str(model_name),
            object_id=str(object_id) if object_id else None,
            object_repr=object_repr,
            description=f"{request.user.username} delete {model_name}: {object_repr[:100]}",
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
        )
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.warning("Error tidak terduga: %s", e)


def capture_old_state(sender, instance, **kwargs):
    """Menyimpan state lama instance sebelum disave untuk pelacakan perubahan"""
    try:
        if sender == UserActivity:
            return
        
        # Hanya untuk objek yang sudah ada di database (bukan objek baru)
        if instance.pk:
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                # Query database — ambil satu data old_instance
                old_instance = sender.objects.get(pk=instance.pk)
                instance._old_state = old_instance
            # Tangkap error sender.DoesNotExist — lanjutkan tanpa crash
            except sender.DoesNotExist:
                instance._old_state = None
        else:
            instance._old_state = None
    except Exception as e:
        logger.warning("Gagal mengirim email: %s", e)


# Register signals untuk semua models kecuali yang excluded
def register_signals():
    """Mendaftarkan signals untuk semua model yang relevan (exclude model tertentu)"""
    from django.apps import apps
    
    EXCLUDED_APPS = ['admin', 'auth', 'contenttypes', 'sessions', 'activity_log']
    EXCLUDED_MODELS = ['LogEntry', 'Permission', 'Group', 'ContentType', 'Session', 'UserActivity']
    
    for model in apps.get_models():
        app_label = model._meta.app_label
        model_name = model.__name__
        
        if app_label in EXCLUDED_APPS or model_name in EXCLUDED_MODELS:
            continue
        
        # Register signals
        pre_save.connect(capture_old_state, sender=model, weak=False)
        post_save.connect(log_model_change, sender=model, weak=False)
        post_delete.connect(log_model_delete, sender=model, weak=False)
