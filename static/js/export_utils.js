

function _isWebView() {
    var ua = navigator.userAgent || '';
    if (window.Capacitor) return true;
    if (/wv|WebView/i.test(ua)) return true;
    if (/Android.*Version\/[\d.]+/i.test(ua) && !/Chrome\/[\d.]+/i.test(ua)) return true;
    if (/iPhone|iPad|iPod/i.test(ua) && !/Safari/i.test(ua)) return true;
    return false;
}


function _downloadBlob(blob, filename) {
    if (_isWebView()) {
        
        
        _downloadBlobWebView(blob, filename);
    } else {
        
        
        _downloadBlobBrowser(blob, filename);
    }
}


function _downloadBlobWebView(blob, filename) {
    
    
    if (navigator.share && navigator.canShare) {
        try {
            var file = new File([blob], filename, { type: blob.type });
            var shareData = { files: [file], title: filename };

            if (navigator.canShare(shareData)) {
                navigator.share(shareData)
                    .then(function() {
                        console.log('File berhasil di-share/download via native share');
                    })
                    .catch(function(err) {
                        
                        if (err.name !== 'AbortError') {
                            console.warn('Share gagal, mencoba fallback:', err);
                            _showManualDownloadLink(blob, filename);
                        }
                    });
                return; 
            }
        } catch (e) {
            console.warn('navigator.share error:', e);
        }
    }

    
    _showManualDownloadLink(blob, filename);
}


function _downloadBlobBrowser(blob, filename) {
    try {
        var url = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        setTimeout(function () {
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        }, 300);
    } catch (e) {
        console.error('Download browser gagal:', e);
        
        _showManualDownloadLink(blob, filename);
    }
}


function _showManualDownloadLink(blob, filename) {
    
    var blobUrl = URL.createObjectURL(blob);

    var overlay = document.createElement('div');
    overlay.className = 'download-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:99999;display:flex;align-items:center;justify-content:center;padding:20px;';
    overlay.innerHTML =
        '<div style="background:#fff;border-radius:16px;padding:28px 24px;text-align:center;max-width:360px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,0.3);">' +
            '<div style="width:60px;height:60px;margin:0 auto 16px;background:linear-gradient(135deg,#e8e8ff,#d0d0ff);border-radius:50%;display:flex;align-items:center;justify-content:center;">' +
                '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#696cff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
            '</div>' +
            '<h5 style="margin:0 0 8px;color:#333;font-size:1.1rem;font-weight:700;">File Siap Diunduh</h5>' +
            '<p style="color:#697a8d;font-size:0.85rem;margin-bottom:20px;line-height:1.4;">Ketuk tombol di bawah untuk menyimpan file <strong>' + filename + '</strong></p>' +
            '<a id="_dl_link" href="' + blobUrl + '" download="' + filename + '" ' +
                'style="display:block;background:linear-gradient(135deg,#696cff,#5f61e6);color:#fff;padding:14px 24px;border-radius:10px;text-decoration:none;font-weight:600;font-size:0.95rem;margin-bottom:12px;">' +
                '📥 Download ' + filename +
            '</a>' +
            '<button id="_dl_close" style="background:none;border:none;color:#697a8d;cursor:pointer;font-size:0.8rem;padding:8px 16px;">Tutup</button>' +
        '</div>';

    
    overlay.querySelector('#_dl_close').addEventListener('click', function () {
        overlay.remove();
        URL.revokeObjectURL(blobUrl);
    });
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) {
            overlay.remove();
            URL.revokeObjectURL(blobUrl);
        }
    });

    
    overlay.querySelector('#_dl_link').addEventListener('click', function () {
        setTimeout(function () {
            overlay.remove();
            
            setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 5000);
        }, 1000);
    });

    document.body.appendChild(overlay);
}


window._downloadBlob = _downloadBlob;
window._isWebView = _isWebView;
window._showManualDownloadLink = _showManualDownloadLink;


function exportTableToExcel(tableId, filename) {
    try {
        const table = document.getElementById(tableId);
        if (!table) {
            alert('Tabel tidak ditemukan!');
            return;
        }

        let csv = [];

        
        const headerRow = table.querySelector('thead tr');
        if (headerRow) {
            const headers = [];
            headerRow.querySelectorAll('th').forEach(th => {
                headers.push('"' + th.textContent.trim().replace(/"/g, '""') + '"');
            });
            csv.push(headers.join(','));
        }

        
        const tbody = table.querySelector('tbody');
        if (tbody) {
            tbody.querySelectorAll('tr').forEach(tr => {
                const cells = tr.querySelectorAll('td');
                if (cells.length === 0) return;
                if (cells.length === 1 && cells[0].colSpan > 1) return;

                const row = [];
                cells.forEach(td => {
                    let text = td.textContent.trim();
                    text = text.replace(/\s+/g, ' ').replace(/"/g, '""');
                    row.push('"' + text + '"');
                });
                csv.push(row.join(','));
            });
        }

        
        const tfoot = table.querySelector('tfoot');
        if (tfoot) {
            tfoot.querySelectorAll('tr').forEach(tr => {
                const cells = tr.querySelectorAll('td, th');
                if (cells.length === 0) return;
                const row = [];
                cells.forEach(cell => {
                    let text = cell.textContent.trim();
                    text = text.replace(/\s+/g, ' ').replace(/"/g, '""');
                    row.push('"' + text + '"');
                });
                csv.push(row.join(','));
            });
        }

        
        const csvContent = csv.join('\n');
        const BOM = '\uFEFF';
        const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });

        
        _downloadBlob(blob, filename + '.csv');

    } catch (error) {
        console.error('Export Excel error:', error);
        alert('Terjadi kesalahan saat export Excel: ' + error.message);
    }
}


function exportTableToPDF(tableId, filename, title, orientation) {
    orientation = orientation || 'landscape';
    try {
        if (typeof pdfMake === 'undefined') {
            alert('pdfMake library tidak tersedia. Export PDF dibatalkan.');
            return;
        }

        const table = document.getElementById(tableId);
        if (!table) {
            alert('Tabel tidak ditemukan!');
            return;
        }

        
        const headers = [];
        const headerRow = table.querySelector('thead tr');
        if (headerRow) {
            headerRow.querySelectorAll('th').forEach(th => {
                headers.push({
                    text: th.textContent.trim(),
                    style: 'tableHeader',
                    fillColor: '#696CFF',
                    color: '#FFFFFF',
                    bold: true
                });
            });
        }

        
        const body = [headers];
        const tbody = table.querySelector('tbody');
        if (tbody) {
            tbody.querySelectorAll('tr').forEach(tr => {
                const cells = tr.querySelectorAll('td');
                if (cells.length === 0) return;
                if (cells.length === 1 && cells[0].colSpan > 1) return;

                const row = [];
                cells.forEach(td => {
                    let text = td.textContent.trim();
                    text = text.replace(/\s+/g, ' ');
                    if (text.length > 100) {
                        text = text.substring(0, 97) + '...';
                    }
                    row.push(text);
                });
                body.push(row);
            });
        }

        
        const tfoot = table.querySelector('tfoot');
        if (tfoot) {
            tfoot.querySelectorAll('tr').forEach(tr => {
                const cells = tr.querySelectorAll('td, th');
                if (cells.length === 0) return;
                const row = [];
                cells.forEach(cell => {
                    let text = cell.textContent.trim();
                    text = text.replace(/\s+/g, ' ');
                    if (text.length > 100) {
                        text = text.substring(0, 97) + '...';
                    }
                    row.push({ text: text, bold: true, fillColor: '#E8E8FF' });
                });
                body.push(row);
            });
        }

        const docDefinition = {
            pageOrientation: orientation,
            pageMargins: [40, 60, 40, 60],
            content: [
                {
                    text: title,
                    style: 'header',
                    margin: [0, 0, 0, 20]
                },
                {
                    table: {
                        headerRows: 1,
                        widths: Array(headers.length).fill('auto'),
                        body: body
                    },
                    layout: {
                        fillColor: function (rowIndex) {
                            return (rowIndex === 0) ? '#696CFF' : ((rowIndex % 2 === 0) ? '#F5F5F9' : null);
                        },
                        hLineWidth: function () { return 0.5; },
                        vLineWidth: function () { return 0.5; },
                        hLineColor: function () { return '#DBDADE'; },
                        vLineColor: function () { return '#DBDADE'; },
                    }
                },
                {
                    text: 'Dicetak pada: ' + new Date().toLocaleString('id-ID'),
                    style: 'footer',
                    margin: [0, 20, 0, 0]
                }
            ],
            styles: {
                header: { fontSize: 18, bold: true, color: '#5F61E6' },
                tableHeader: { bold: true, fontSize: 11, color: '#FFFFFF' },
                footer: { fontSize: 9, italics: true, color: '#697A8D' }
            },
            defaultStyle: { fontSize: 9 }
        };

        
        var pdfDoc = pdfMake.createPdf(docDefinition);

        if (_isWebView()) {
            pdfDoc.getBlob(function (blob) {
                _downloadBlob(blob, filename + '.pdf');
            });
        } else {
            pdfDoc.download(filename + '.pdf');
        }

    } catch (error) {
        console.error('Export PDF error:', error);
        alert('Terjadi kesalahan saat export PDF: ' + error.message);
    }
}


(function() {
    'use strict';

    
    if (!_isWebView()) return;

    
    var _originalClick = HTMLAnchorElement.prototype.click;

    
    HTMLAnchorElement.prototype.click = function() {
        
        var downloadAttr = this.getAttribute('download');
        var href = this.href || '';

        if (downloadAttr && (href.startsWith('blob:') || href.startsWith('data:'))) {
            
            var filename = downloadAttr || 'download';

            console.log('[DownloadInterceptor] Intercepted download: ' + filename);

            if (href.startsWith('blob:')) {
                
                fetch(href)
                    .then(function(response) { return response.blob(); })
                    .then(function(blob) {
                        _downloadBlob(blob, filename);
                    })
                    .catch(function(err) {
                        console.error('[DownloadInterceptor] Fetch blob gagal:', err);
                        
                        _originalClick.call(this);
                    }.bind(this));
            } else if (href.startsWith('data:')) {
                
                try {
                    var parts = href.split(',');
                    var meta = parts[0]; 
                    var raw = parts[1];
                    var mimeMatch = meta.match(/data:([^;]+)/);
                    var mime = mimeMatch ? mimeMatch[1] : 'application/octet-stream';
                    var isBase64 = meta.indexOf('base64') !== -1;

                    var byteString;
                    if (isBase64) {
                        byteString = atob(raw);
                    } else {
                        byteString = decodeURIComponent(raw);
                    }

                    var ab = new ArrayBuffer(byteString.length);
                    var ia = new Uint8Array(ab);
                    for (var i = 0; i < byteString.length; i++) {
                        ia[i] = byteString.charCodeAt(i);
                    }

                    var blob = new Blob([ab], { type: mime });
                    _downloadBlob(blob, filename);
                } catch (e) {
                    console.error('[DownloadInterceptor] Data URI parse gagal:', e);
                    _originalClick.call(this);
                }
            }

            return; 
        }

        
        _originalClick.call(this);
    };

    console.log('[ExportUtils] Global download interceptor aktif untuk WebView');
})();
