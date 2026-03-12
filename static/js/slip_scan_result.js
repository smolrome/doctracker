function printQR() {
  const img = document.querySelector('.next-qr-box img');
  if (!img) return;
  const w = window.open('', '_blank', 'width=400,height=500');
  w.document.write(`<html><body style="text-align:center;padding:20px;font-family:sans-serif">
    <h3 style="margin-bottom:12px;">📤 RELEASE QR — Routing Slip</h3>
    <p style="font-size:13px;color:#666;margin-bottom:16px;">Scan when documents leave this office</p>
    <img src="${img.src}" style="width:260px;border:2px solid #ccc;border-radius:8px;"/>
    <script>window.onload=function(){window.print();}<\/script>
  </body></html>`);
  w.document.close();
}
