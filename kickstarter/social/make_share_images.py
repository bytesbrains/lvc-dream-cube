"""Build share images with Kickstarter's official campaign-stage banners.

Kickstarter's creator kit banners (docs/img/kickstarter/English - <Stage>/)
are made to sit along the bottom edge of a photo. This script puts them on
our real prototype photo and writes:

  docs/img/og-kickstarter.jpg          1200x630 link preview for the landing page
  kickstarter/social/<stage>-<platform>.jpg   post images for Instagram and X

Usage: python make_share_images.py [--stage "Just Launched"] [--fonts DIR]
DIR must hold Baloo2[wght].ttf and AtkinsonHyperlegible-Regular.ttf (Google Fonts).
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
IMG = ROOT / "docs/img"
KIT = IMG / "kickstarter"
OUT = Path(__file__).resolve().parent
PHOTO = IMG / "cube-scrambled.jpg"
BG, INK, MUTED = (255, 248, 238), (29, 26, 46), (85, 80, 107)
# Crop box around the front cube in cube-scrambled.jpg (1200x1600)
CUBE = (60, 300, 1100, 1560)

# platform -> (canvas size, banner file suffix)
POSTS = {
    "instagram": ((1080, 1350), "Instagram"),
    "x": ((1024, 1280), "Twitter"),
}


def cover(img, size, box=None):
    """Crop img (optionally to box first) so it fills size, centred."""
    if box:
        img = img.crop(box)
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - tw) // 2, (img.height - th) // 2
    return img.crop((left, top, left + tw, top + th))


def with_banner(canvas, banner_path):
    banner = Image.open(banner_path).convert("RGBA")
    if banner.width != canvas.width:
        banner = banner.resize((canvas.width, round(banner.height * canvas.width / banner.width)), Image.LANCZOS)
    # The 1200px ("Facebook") and Instagram banners run the bar along their top row
    # (badge hangs down), so they belong on the photo's top edge; the X banner sits on the bottom.
    top_edge = banner.getpixel((banner.width - 1, 0))[3] > 0
    canvas = canvas.convert("RGBA")
    canvas.alpha_composite(banner, (0, 0 if top_edge else canvas.height - banner.height))
    return canvas.convert("RGB")


def og_image(stage, fonts):
    w, h = 1200, 630
    canvas = Image.new("RGB", (w, h), BG)
    photo_w = 520
    canvas.paste(cover(Image.open(PHOTO), (photo_w, h), CUBE), (w - photo_w, 0))
    d = ImageDraw.Draw(canvas)
    baloo = ImageFont.truetype(str(fonts / "Baloo2[wght].ttf"), 64)
    baloo.set_variation_by_name("ExtraBold")
    body = ImageFont.truetype(str(fonts / "AtkinsonHyperlegible-Regular.ttf"), 34)
    logo = Image.open(IMG / "lvc-logo.png").convert("RGBA").resize((72, 72), Image.LANCZOS)
    # Kickstarter's 1200px-wide banner (its kit calls it the Facebook size) fits the
    # link preview exactly. Its badge fills the top-left corner, so the text starts below it.
    x = 56
    y = 212
    for line in ("A puzzle cube you", "can solve by touch."):
        d.text((x, y), line, font=baloo, fill=INK)
        y += 72
    d.text((x, y + 14), "Every colour has its own texture.", font=body, fill=MUTED)
    canvas.paste(logo, (x, 520), logo)
    d.text((x + 88, 534), "LVC Dream", font=body, fill=MUTED)
    return with_banner(canvas, KIT / f"English - {stage}/{stage}_English_Facebook.png")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", default="Just Launched",
                   choices=["Just Launched", "Nearly Funded", "Ending Soon", "Just Funded"])
    p.add_argument("--fonts", type=Path, required=True)
    a = p.parse_args()
    slug = a.stage.lower().replace(" ", "-")
    og_image(a.stage, a.fonts).save(IMG / "og-kickstarter.jpg", quality=88, optimize=True)
    for platform, (size, suffix) in POSTS.items():
        img = cover(Image.open(PHOTO), size, CUBE)
        img = with_banner(img, KIT / f"English - {a.stage}/{a.stage}_English_{suffix}.png")
        img.save(OUT / f"{slug}-{platform}.jpg", quality=88, optimize=True)
    print("wrote", IMG / "og-kickstarter.jpg", "and", len(POSTS), "post images")


if __name__ == "__main__":
    main()
