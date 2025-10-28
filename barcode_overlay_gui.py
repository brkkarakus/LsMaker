import re
from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit

PAGE_W, PAGE_H = A4
MARGIN = 36                  # 0.5 inch
BARCODE_TARGET_W = 360.0     # barcode hedef genişliği (pt) ~ 12.7 cm
GAP_BARCODE_LABEL = 14.0     # barcode altı ile etiket arası (pt)
TOP_TEXT_FONT = ("Helvetica", 10)
LABEL_FONT = ("Helvetica", 12)

def sanitize_filename(name: str) -> str:
    name = name.strip()
    # Türkçe karakterleri koru, yasak karakterleri tireye çevir
    name = re.sub(r'[\\/:"*?<>|]+', "-", name)
    # Çoklu boşlukları tek boşluk, baş/son boşlukları kırp
    name = re.sub(r"\s+", " ", name).strip()
    # Çok uzun olmasın
    return name[:120] if name else "output"

def draw_base_a4_with_text_and_label(top_text: str, label_text: str, barcode_w_pt: float, barcode_h_pt: float):
    """
    A4 tek sayfalık bir PDF üretir: en üste TXT metni, ortada barcode alanı (şimdilik çizilmez),
    barcode'un hemen altına etiket yazılır. Etiket konumu, barcode yerleşimine göre hesaplanır.
    """
    # Barcode'u sayfa ortasına yerleştireceğiz
    x = (PAGE_W - barcode_w_pt) / 2.0
    y = (PAGE_H - barcode_h_pt) / 2.0

    # Etiket konumu: barcode altından küçük bir boşlukla
    label_x_center = PAGE_W / 2.0
    label_y = y - GAP_BARCODE_LABEL

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # 1) Üst metin (TXT) — üstten aşağı doğru, kenarlardan MARGIN
    font_name, font_size = TOP_TEXT_FONT
    c.setFont(font_name, font_size)
    available_width = PAGE_W - 2 * MARGIN
    line_height = font_size * 1.3
    y_text = PAGE_H - MARGIN

    wrapped_lines = []
    for paragraph in (top_text.splitlines() or [""]):
        lines = simpleSplit(paragraph if paragraph else " ", font_name, font_size, available_width)
        wrapped_lines.extend(lines if lines else [""])

    for line in wrapped_lines:
        if y_text - line_height < MARGIN:
            break
        c.drawString(MARGIN, y_text - line_height, line)
        y_text -= line_height

    # 2) Etiket (barcode altına)
    c.setFont(LABEL_FONT[0], LABEL_FONT[1])
    c.drawCentredString(label_x_center, label_y, label_text)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read(), (x, y)

def compose_final_pdf(barcode_pdf_path: Path, txt_path: Path, label_text: str, out_dir: Path = None):
    # TXT oku
    top_text = txt_path.read_text(encoding="utf-8", errors="replace")

    # Barcode PDF ilk sayfa boyutu
    bc_reader = PdfReader(str(barcode_pdf_path))
    bc_page = bc_reader.pages[0]
    bc_w = float(bc_page.mediabox.width)
    bc_h = float(bc_page.mediabox.height)

    # Ölçek: hedef genişliğe göre
    scale = BARCODE_TARGET_W / bc_w
    barcode_w_pt = bc_w * scale
    barcode_h_pt = bc_h * scale

    # A4 temel sayfa: üst metin + etiket (barcode henüz basılmadı)
    base_bytes, (x, y) = draw_base_a4_with_text_and_label(top_text, label_text, barcode_w_pt, barcode_h_pt)

    # Base PDF'i oku ve barcode sayfasını A4'e ortala + ölçekle
    base_reader = PdfReader(BytesIO(base_bytes))
    base_page = base_reader.pages[0]

    # Barcode'u (ölçeklenmiş) A4'e yerleştir
    t = Transformation().scale(scale).translate(x, y)
    base_page.merge_transformed_page(bc_page, t)

    writer = PdfWriter()
    writer.add_page(base_page)

    # Çıktı dosya adı: label_text (sanitize)
    out_name = sanitize_filename(label_text) + ".pdf"
    target_dir = out_dir if out_dir else barcode_pdf_path.parent
    out_path = target_dir / out_name

    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path

# -------------------- GUI --------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("A4 PDF Composer: Top Text + Center Barcode + Label")
        self.geometry("960x640")
        self.minsize(720, 480)
        self.resizable(True, True)
        self.attributes("-fullscreen", False)
        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", self.exit_fullscreen)

        self.src_pdf = tk.StringVar()
        self.txt_file = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.label_text = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_ui()

    def toggle_fullscreen(self, event=None):
        self.attributes("-fullscreen", not self.attributes("-fullscreen"))

    def exit_fullscreen(self, event=None):
        self.attributes("-fullscreen", False)

    def _build_ui(self):
        pad = {"padx": 12, "pady": 8}
        frm = ttk.Frame(self)
        frm.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        frm.columnconfigure(0, weight=0)
        frm.columnconfigure(1, weight=1)
        frm.columnconfigure(2, weight=0)

        # Barcode PDF
        ttk.Label(frm, text="Barcode PDF (ilk sayfa kullanılacak):").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.src_pdf).grid(row=0, column=1, sticky="we", **pad)
        ttk.Button(frm, text="Seç…", command=self.pick_pdf).grid(row=0, column=2, **pad)

        # TXT dosyası (üst metin)
        ttk.Label(frm, text="TXT dosyası (sayfanın en üstüne yazılır):").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.txt_file).grid(row=1, column=1, sticky="we", **pad)
        ttk.Button(frm, text="Seç…", command=self.pick_txt).grid(row=1, column=2, **pad)

        # Etiket (barcode altına) + aynı zamanda dosya adı
        ttk.Label(frm, text="Etiket (barcode altı) ve dosya adı:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.label_text).grid(row=2, column=1, sticky="we", **pad)

        # Çıktı klasörü (opsiyonel)
        ttk.Label(frm, text="Çıktı klasörü (ops.):").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.out_dir).grid(row=3, column=1, sticky="we", **pad)
        ttk.Button(frm, text="Seç…", command=self.pick_out_dir).grid(row=3, column=2, **pad)

        # Aksiyonlar
        actions = ttk.Frame(frm)
        actions.grid(row=4, column=0, columnspan=3, sticky="we", **pad)
        ttk.Button(actions, text="PDF Oluştur", command=self.create_pdf).grid(row=0, column=0, **pad)
        ttk.Button(actions, text="Kapat", command=self.destroy).grid(row=0, column=1, **pad)

        self.status = ttk.Label(frm, text="A4 sayfa: üstte TXT, ortada barcode, altında etiket. Dosya adı = etiket.")
        self.status.grid(row=5, column=0, columnspan=3, sticky="w", padx=12, pady=(4, 0))

    def pick_pdf(self):
        p = filedialog.askopenfilename(title="Barcode PDF seç", filetypes=[("PDF", "*.pdf"), ("Tümü", "*.*")])
        if p: self.src_pdf.set(p)

    def pick_txt(self):
        p = filedialog.askopenfilename(title="TXT dosyası seç", filetypes=[("Text", "*.txt"), ("Tümü", "*.*")])
        if p: self.txt_file.set(p)

    def pick_out_dir(self):
        p = filedialog.askdirectory(title="Çıktı klasörü seç")
        if p: self.out_dir.set(p)

    def create_pdf(self):
        try:
            src = self.src_pdf.get().strip()
            txt = self.txt_file.get().strip()
            label = self.label_text.get().strip()

            if not src or not Path(src).exists():
                messagebox.showerror("Hata", "Geçerli bir Barcode PDF seçin.")
                return
            if not txt or not Path(txt).exists():
                messagebox.showerror("Hata", "Geçerli bir TXT dosyası seçin.")
                return
            if not label:
                messagebox.showerror("Hata", "Etiket metni zorunludur (dosya adı olarak kullanılacak).")
                return

            out_dir = Path(self.out_dir.get().strip()) if self.out_dir.get().strip() else None
            out_path = compose_final_pdf(Path(src), Path(txt), label, out_dir)
            self.status.configure(text=f"✅ Oluşturuldu: {out_path}")
            messagebox.showinfo("Başarılı", f"PDF oluşturuldu:\n{out_path}")
        except Exception as e:
            self.status.configure(text=f"Hata: {e}")
            messagebox.showerror("Hata", f"PDF oluşturulamadı:\n{e}")

if __name__ == "__main__":
    App().mainloop()

