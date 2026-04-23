import sys
import fitz

def extract_pdf_text(pdf_path, txt_path):
    doc = fitz.open(pdf_path)
    with open(txt_path, "w", encoding="utf-8") as f:
        for i, page in enumerate(doc):
            f.write(f"--- Page {i + 1} ---\n")
            f.write(page.get_text())
            f.write("\n\n")

if __name__ == "__main__":
    extract_pdf_text(sys.argv[1], "pdf_output.txt")
