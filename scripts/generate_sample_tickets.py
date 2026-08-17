"""Generate synthetic waste intake ticket images for testing the extraction agent.
Not real scanned documents - drawn to look like a filled-in paper weighbridge ticket
so the demo has something concrete to upload without needing a real company's data.
"""
import os

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "sample_tickets")
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "samples")


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in ["arial.ttf", "C:\\Windows\\Fonts\\arial.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_ticket(path: str, fields: dict, messy: bool = False) -> None:
    img = Image.new("RGB", (900, 650), "white")
    d = ImageDraw.Draw(img)
    title_font = _font(30)
    label_font = _font(20)
    value_font = _font(22)

    d.rectangle([20, 20, 880, 630], outline="black", width=3)
    d.text((40, 40), "WEIGHBRIDGE - INTAKE TICKET", font=title_font, fill="black")
    d.line([40, 90, 860, 90], fill="black", width=2)

    y = 130
    for label, value in fields.items():
        d.text((60, y), f"{label}:", font=label_font, fill="black")
        fill = "black"
        if messy and label == "Truck / Driver ID":
            fill = "gray"  # simulate faded/smudged handwriting
        d.text((320, y - 2), str(value), font=value_font, fill=fill)
        y += 60

    d.text((60, 560), "Signed: ___________________", font=label_font, fill="black")
    img.save(path)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(PUBLIC_DIR, exist_ok=True)

    draw_ticket(
        os.path.join(OUT_DIR, "ticket_clean.png"),
        {
            "Source / Farm": "Al Ain Date Farms Co.",
            "Material": "Date Palm Fronds",
            "Net Weight (kg)": "8420",
            "Truck / Driver ID": "DXB-44215 / A. Rahman",
            "Delivery Date": "2026-08-12",
            "Notes": "Standard delivery, no damage",
        },
    )

    draw_ticket(
        os.path.join(OUT_DIR, "ticket_messy.png"),
        {
            "Source / Farm": "Liwa Palm Cooperative",
            "Material": "Date Seed Kernels",
            "Net Weight (kg)": "61500",
            "Truck / Driver ID": "??? smudged ???",
            "Delivery Date": "2026-08-15",
            "Notes": "Partial load, second trip pending",
        },
        messy=True,
    )

    import shutil
    for name in ["ticket_clean.png", "ticket_messy.png"]:
        shutil.copyfile(os.path.join(OUT_DIR, name), os.path.join(PUBLIC_DIR, name))

    print(f"wrote sample tickets to {os.path.abspath(OUT_DIR)} and {os.path.abspath(PUBLIC_DIR)}")


if __name__ == "__main__":
    main()
