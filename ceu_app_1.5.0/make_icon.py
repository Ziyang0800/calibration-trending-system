"""Make app.ico from your own picture:   python make_icon.py logo.png
(square PNG, at least 256x256 works best). Without an argument it draws the default red icon."""
import sys
from PIL import Image, ImageDraw

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

if len(sys.argv) > 1:
    img = Image.open(sys.argv[1]).convert("RGBA")
    side = max(img.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    img = sq.resize((256, 256), Image.LANCZOS)
else:
    # default icon: red tile, white viewfinder corners, barcode and a scan line (drawn at 4x, then reduced)
    K = 4
    big = Image.new("RGBA", (256 * K, 256 * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    u = lambda v: int(v * K)
    d.rounded_rectangle((u(8), u(8), u(248), u(248)), radius=u(52), fill=(233, 0, 41, 255))
    white, w = (255, 255, 255, 255), u(13)
    a, b, n = 58, 198, 44                                   # corner box and corner length
    for (x, y, sx, sy) in ((a, a, 1, 1), (b, a, -1, 1), (a, b, 1, -1), (b, b, -1, -1)):
        d.line([(u(x), u(y + sy * n)), (u(x), u(y)), (u(x + sx * n), u(y))], fill=white, width=w, joint="curve")
        for px, py in ((x, y + sy * n), (x + sx * n, y)):   # round the line ends
            d.ellipse((u(px) - w // 2, u(py) - w // 2, u(px) + w // 2, u(py) + w // 2), fill=white)
        d.ellipse((u(x) - w // 2, u(y) - w // 2, u(x) + w // 2, u(y) + w // 2), fill=white)
    x = 72                                                  # barcode bars: (width, gap)
    for bw, gap in ((9, 6), (5, 6), (14, 6), (5, 6), (9, 6), (5, 6), (14, 6), (9, 0)):
        d.rectangle((u(x), u(84), u(x + bw), u(172)), fill=white)
        x += bw + gap
    d.rounded_rectangle((u(40), u(122), u(216), u(134)), radius=u(6), fill=(18, 18, 22, 255))   # scan line
    img = big.resize((256, 256), Image.LANCZOS)
img.save("app.ico", sizes=SIZES)
print("Saved app.ico - run build_exe.bat again")
