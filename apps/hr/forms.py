"""
==========================================================================
 HR FORMS - Form untuk modul HR (SDM)
==========================================================================
 1. DepartemenForm → CRUD departemen (kode, nama, kepala)
 2. JabatanForm → CRUD jabatan (kode, nama, gaji_pokok, tunjangan)
 3. KaryawanForm → CRUD karyawan (NIK auto-generate, data personal)
 4. AbsensiForm → Absensi manual (karyawan, tanggal, jam, status)
 5. PenggajianForm → Slip gaji individual (komponen gaji + potongan)
 6. FotoWajahForm → Upload foto wajah untuk face recognition
 7. GeneratePenggajianForm → Generate slip gaji MASSAL (bulan, tahun, tunjangan)
 8. PengaturanAbsensiForm → Pengaturan absensi (jam, lokasi GPS, hari kerja)

 Fitur khusus PengaturanAbsensiForm:
 - hari_kerja_checkboxes: MultipleChoiceField → disimpan sebagai CSV string
 - Default hari kerja: Senin-Jumat (0-4)
 - Custom save(): konversi list checkbox ke string 'hari_kerja'
==========================================================================
"""

# Import dari framework Django
from django import forms
# Import dari modul internal proyek
from apps.hr.models import Departemen, Jabatan, Karyawan, Absensi, Penggajian, FotoWajah, PengaturanAbsensi


class DepartemenForm(forms.ModelForm):
    """Form untuk Departemen"""
    class Meta:
        """Konfigurasi form Departemen — field dan widget Bootstrap."""
        model = Departemen
        fields = ['kode', 'nama', 'deskripsi', 'kepala_departemen', 'aktif']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'kode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kode Departemen'}),
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Departemen'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Deskripsi'}),
            'kepala_departemen': forms.Select(attrs={'class': 'form-select'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class JabatanForm(forms.ModelForm):
    """Form untuk Jabatan"""
    class Meta:
        """Konfigurasi form Jabatan — field termasuk gaji dan tunjangan."""
        model = Jabatan
        fields = ['kode', 'nama', 'departemen', 'level', 'gaji_pokok', 'tunjangan_jabatan', 'deskripsi', 'aktif']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'kode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kode Jabatan'}),
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Jabatan'}),
            'departemen': forms.Select(attrs={'class': 'form-select'}),
            'level': forms.Select(attrs={'class': 'form-select'}),
            'gaji_pokok': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'tunjangan_jabatan': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Deskripsi Tugas'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class KaryawanForm(forms.ModelForm):
    """Form untuk Karyawan"""
    class Meta:
        """Konfigurasi form Karyawan — mencakup data personal, jabatan, dan gaji."""
        model = Karyawan
        fields = [
            'nik', 'nama', 'email', 'telepon', 'alamat',
            'tempat_lahir', 'tanggal_lahir', 'jenis_kelamin',
            'foto', 'jabatan', 'departemen', 'cabang', 'tanggal_masuk',
            'gaji_pokok', 'status', 'aktif'
        ]
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'nik': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'NIK Karyawan (auto-generate jika kosong)'}),
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Lengkap'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'telepon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Telepon'}),
            'alamat': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Alamat Lengkap'}),
            'tempat_lahir': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tempat Lahir'}),
            'tanggal_lahir': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-select'}),
            'foto': forms.FileInput(attrs={'class': 'form-control'}),
            'jabatan': forms.Select(attrs={'class': 'form-select'}),
            'departemen': forms.Select(attrs={'class': 'form-select'}),
            'cabang': forms.Select(attrs={'class': 'form-select'}),
            'tanggal_masuk': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gaji_pokok': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class AbsensiForm(forms.ModelForm):
    """Form untuk Absensi Manual"""
    class Meta:
        """Konfigurasi form Absensi — karyawan, tanggal, jam, dan status."""
        model = Absensi
        fields = ['karyawan', 'tanggal', 'jam_masuk', 'jam_keluar', 'status', 'catatan']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'karyawan': forms.Select(attrs={'class': 'form-select'}),
            'tanggal': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'jam_masuk': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'jam_keluar': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'catatan': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Catatan'}),
        }


class PenggajianForm(forms.ModelForm):
    """Form untuk Generate Penggajian"""
    class Meta:
        """Konfigurasi form Penggajian — semua komponen pendapatan dan potongan."""
        model = Penggajian
        fields = [
            'karyawan', 'periode_bulan', 'periode_tahun',
            'gaji_pokok', 'tunjangan_jabatan', 'tunjangan_makan',
            'tunjangan_transport', 'tunjangan_lainnya', 'lembur', 'bonus',
            'potongan_bpjs_kesehatan', 'potongan_bpjs_ketenagakerjaan',
            'potongan_pph21', 'potongan_lainnya', 'catatan'
        ]
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'karyawan': forms.Select(attrs={'class': 'form-select'}),
            'periode_bulan': forms.Select(attrs={'class': 'form-select'}, choices=[
                (1, 'Januari'), (2, 'Februari'), (3, 'Maret'), (4, 'April'),
                (5, 'Mei'), (6, 'Juni'), (7, 'Juli'), (8, 'Agustus'),
                (9, 'September'), (10, 'Oktober'), (11, 'November'), (12, 'Desember')
            ]),
            'periode_tahun': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '2026'}),
            'gaji_pokok': forms.NumberInput(attrs={'class': 'form-control'}),
            'tunjangan_jabatan': forms.NumberInput(attrs={'class': 'form-control'}),
            'tunjangan_makan': forms.NumberInput(attrs={'class': 'form-control'}),
            'tunjangan_transport': forms.NumberInput(attrs={'class': 'form-control'}),
            'tunjangan_lainnya': forms.NumberInput(attrs={'class': 'form-control'}),
            'lembur': forms.NumberInput(attrs={'class': 'form-control'}),
            'bonus': forms.NumberInput(attrs={'class': 'form-control'}),
            'potongan_bpjs_kesehatan': forms.NumberInput(attrs={'class': 'form-control'}),
            'potongan_bpjs_ketenagakerjaan': forms.NumberInput(attrs={'class': 'form-control'}),
            'potongan_pph21': forms.NumberInput(attrs={'class': 'form-control'}),
            'potongan_lainnya': forms.NumberInput(attrs={'class': 'form-control'}),
            'catatan': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class FotoWajahForm(forms.ModelForm):
    """Form untuk upload foto wajah"""
    class Meta:
        """Konfigurasi form upload foto wajah — field karyawan dan file foto."""
        model = FotoWajah
        fields = ['karyawan', 'foto']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'karyawan': forms.Select(attrs={'class': 'form-select'}),
            'foto': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }


class GeneratePenggajianForm(forms.Form):
    """Form untuk generate penggajian bulanan"""
    periode_bulan = forms.ChoiceField(
        choices=[
            (1, 'Januari'), (2, 'Februari'), (3, 'Maret'), (4, 'April'),
            (5, 'Mei'), (6, 'Juni'), (7, 'Juli'), (8, 'Agustus'),
            (9, 'September'), (10, 'Oktober'), (11, 'November'), (12, 'Desember')
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    periode_tahun = forms.IntegerField(
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '2026'})
    )
    tunjangan_makan = forms.DecimalField(
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '500000'})
    )
    tunjangan_transport = forms.DecimalField(
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '300000'})
    )


class PengaturanAbsensiForm(forms.ModelForm):
    """Form untuk pengaturan absensi"""
    
    HARI_CHOICES = [
        ('0', 'Senin'),
        ('1', 'Selasa'),
        ('2', 'Rabu'),
        ('3', 'Kamis'),
        ('4', 'Jumat'),
        ('5', 'Sabtu'),
        ('6', 'Minggu'),
    ]
    
    hari_kerja_checkboxes = forms.MultipleChoiceField(
        choices=HARI_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label="Hari Kerja"
    )
    
    # Konfigurasi metadata model/form
    class Meta:
        """Konfigurasi form pengaturan absensi — jam kerja, lokasi GPS, dan fitur wajib."""
        model = PengaturanAbsensi
        fields = [
            'nama', 'aktif', 'cabang',
            'jam_masuk', 'jam_pulang', 'toleransi_terlambat',
            'zona_waktu', 'nama_lokasi', 'alamat_lokasi',
            'latitude', 'longitude', 'radius_lokasi',
            'wajib_foto', 'wajib_lokasi', 'wajib_face_recognition',
            'mulai_lembur_setelah', 'catatan'
        ]
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Pengaturan'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'cabang': forms.Select(attrs={'class': 'form-select'}),
            'jam_masuk': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'jam_pulang': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'toleransi_terlambat': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '15'}),
            'zona_waktu': forms.Select(attrs={'class': 'form-select'}),
            'nama_lokasi': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Kantor'}),
            'alamat_lokasi': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Alamat Lengkap'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '-6.2088', 'step': '0.0000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '106.8456', 'step': '0.0000001'}),
            'radius_lokasi': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '100'}),
            'wajib_foto': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'wajib_lokasi': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'wajib_face_recognition': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'mulai_lembur_setelah': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'catatan': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Catatan'}),
        }
    
    def __init__(self, *args, **kwargs):
        """Inisialisasi form — set nilai awal checkbox hari kerja dari data model atau default Senin-Jumat."""
        super().__init__(*args, **kwargs)
        # Set nilai awal untuk hari_kerja_checkboxes dari model
        if self.instance and self.instance.pk:
            if self.instance.hari_kerja:
                self.fields['hari_kerja_checkboxes'].initial = self.instance.hari_kerja.split(',')
        else:
            # Default: Senin - Jumat
            self.fields['hari_kerja_checkboxes'].initial = ['0', '1', '2', '3', '4']
    
    def save(self, commit=True):
        """Override save — konversi list checkbox hari kerja ke string CSV sebelum simpan."""
        instance = super().save(commit=False)
        # Convert checkbox values to comma-separated string
        hari_kerja_list = self.cleaned_data.get('hari_kerja_checkboxes', [])
        instance.hari_kerja = ','.join(hari_kerja_list)
        if commit:
            instance.save()
        return instance
