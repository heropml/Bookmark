from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent / "assets" / "icons"
SIZE = 256
SCALE = 4
CANVAS = SIZE * SCALE

THEMES = {
    "aurora": {
        "bg": (2, 10, 29, 255),
        "bg2": (12, 4, 34, 255),
        "glow1": (0, 214, 255, 215),
        "glow2": (182, 44, 255, 205),
        "mark": ((21, 239, 255, 255), (12, 94, 255, 255), (208, 44, 255, 255)),
    },
    "cyber": {
        "bg": (1, 13, 12, 255),
        "bg2": (4, 5, 12, 255),
        "glow1": (42, 255, 137, 215),
        "glow2": (255, 36, 180, 205),
        "mark": ((70, 255, 151, 255), (12, 178, 145, 255), (255, 42, 185, 255)),
    },
    "ember": {
        "bg": (24, 7, 3, 255),
        "bg2": (12, 3, 7, 255),
        "glow1": (255, 183, 58, 215),
        "glow2": (255, 51, 24, 205),
        "mark": ((255, 222, 99, 255), (255, 111, 21, 255), (255, 37, 37, 255)),
    },
    "paper": {
        "bg": (51, 31, 13, 255),
        "bg2": (22, 12, 8, 255),
        "glow1": (255, 219, 139, 210),
        "glow2": (221, 111, 53, 195),
        "mark": ((255, 239, 190, 255), (220, 158, 83, 255), (177, 68, 42, 255)),
    },
    "nebula": {
        "bg": (5, 5, 28, 255),
        "bg2": (18, 6, 45, 255),
        "glow1": (77, 132, 255, 215),
        "glow2": (194, 82, 255, 205),
        "mark": ((142, 211, 255, 255), (96, 75, 255, 255), (240, 113, 255, 255)),
    },
    "prism": {
        "bg": (2, 16, 28, 255),
        "bg2": (18, 5, 31, 255),
        "glow1": (38, 225, 236, 215),
        "glow2": (244, 75, 175, 205),
        "mark": ((83, 244, 236, 255), (108, 92, 255, 255), (255, 89, 177, 255)),
    },
    "obsidian": {
        "bg": (20, 17, 12, 255),
        "bg2": (4, 4, 3, 255),
        "glow1": (246, 215, 142, 210),
        "glow2": (185, 130, 52, 195),
        "mark": ((255, 244, 203, 255), (229, 184, 91, 255), (145, 91, 28, 255)),
    },
    "abyss": {
        "bg": (2, 35, 53, 255),
        "bg2": (1, 8, 16, 255),
        "glow1": (70, 229, 238, 215),
        "glow2": (37, 211, 177, 205),
        "mark": ((121, 246, 242, 255), (22, 164, 190, 255), (15, 111, 129, 255)),
    },
    "snow": {
        "bg": (249, 251, 254, 255),
        "bg2": (227, 234, 244, 255),
        "glow1": (177, 205, 241, 160),
        "glow2": (198, 186, 231, 140),
        "mark": ((210, 231, 252, 255), (95, 131, 184, 255), (83, 95, 153, 255)),
    },
    "sakura": {
        "bg": (255, 246, 249, 255),
        "bg2": (243, 221, 232, 255),
        "glow1": (255, 183, 211, 170),
        "glow2": (221, 146, 188, 155),
        "mark": ((255, 217, 231, 255), (216, 111, 157, 255), (151, 64, 122, 255)),
    },
    "celadon": {
        "bg": (246, 251, 248, 255),
        "bg2": (223, 236, 229, 255),
        "glow1": (167, 227, 205, 165),
        "glow2": (138, 202, 179, 150),
        "mark": ((210, 246, 228, 255), (79, 156, 128, 255), (44, 108, 87, 255)),
    },
    "shuimo": {
        "bg": (250, 248, 241, 255),
        "bg2": (232, 228, 217, 255),
        "glow1": (176, 184, 176, 135),
        "glow2": (99, 110, 102, 145),
        "mark": ((219, 222, 210, 255), (100, 107, 99, 255), (37, 44, 43, 255)),
    },
    "daiqing": {
        "bg": (220, 238, 229, 255),
        "bg2": (18, 62, 80, 255),
        "glow1": (101, 197, 170, 190),
        "glow2": (27, 125, 112, 175),
        "mark": ((207, 226, 169, 255), (38, 126, 120, 255), (18, 62, 80, 255)),
    },
    "zhusha": {
        "bg": (255, 247, 232, 255),
        "bg2": (239, 221, 190, 255),
        "glow1": (236, 168, 115, 155),
        "glow2": (175, 55, 41, 155),
        "mark": ((255, 216, 164, 255), (212, 81, 52, 255), (168, 43, 36, 255)),
    },
    "yemo": {
        "bg": (20, 30, 43, 255),
        "bg2": (8, 13, 21, 255),
        "glow1": (193, 162, 107, 145),
        "glow2": (75, 103, 127, 115),
        "mark": ((237, 224, 196, 255), (193, 162, 107, 255), (112, 96, 68, 255)),
    },
}


def n(value):
    return int(round(value * SCALE))


def box(values):
    return tuple(n(value) for value in values)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


def gradient(size, stops):
    width, height = size
    out = Image.new("RGBA", size)
    draw = ImageDraw.Draw(out)
    sections = len(stops) - 1
    for y in range(height):
        pos = (y / max(height - 1, 1)) * sections
        section = min(int(pos), sections - 1)
        color = lerp(stops[section], stops[section + 1], pos - section)
        draw.line((0, y, width, y), fill=color)
    return out


def glow_ellipse(image, bounds, color, blur):
    layer = Image.new("RGBA", image.size)
    ImageDraw.Draw(layer).ellipse(box(bounds), fill=color)
    return Image.alpha_composite(image, layer.filter(ImageFilter.GaussianBlur(n(blur))))


def paint(theme):
    outer = Image.new("L", (CANVAS, CANVAS))
    ImageDraw.Draw(outer).rounded_rectangle(box((10, 10, 246, 246)), radius=n(49), fill=255)

    backdrop = gradient((CANVAS, CANVAS), (theme["bg"], theme["bg2"]))
    backdrop.putalpha(outer)
    image = Image.new("RGBA", (CANVAS, CANVAS))
    image = Image.alpha_composite(image, backdrop)

    image = glow_ellipse(image, (27, 30, 180, 184), theme["glow1"], 35)
    image = glow_ellipse(image, (99, 78, 236, 226), theme["glow2"], 35)
    image.putalpha(outer)

    # Deep glass vignette and diagonal reflection inside the rounded tile.
    vignette = Image.new("RGBA", image.size)
    vd = ImageDraw.Draw(vignette)
    vd.rounded_rectangle(box((17, 17, 239, 239)), radius=n(43), outline=(0, 0, 0, 150), width=n(18))
    vd.polygon(
        [(n(18), n(24)), (n(162), n(12)), (n(67), n(238))],
        fill=(255, 255, 255, 13),
    )
    vignette.putalpha(ImageChops.multiply(vignette.getchannel("A"), outer))
    image = Image.alpha_composite(image, vignette)

    # Layered outer rim: a soft neon halo, colored rails and a white glass glint.
    rim = Image.new("RGBA", image.size)
    rd = ImageDraw.Draw(rim)
    rd.rounded_rectangle(box((11, 11, 245, 245)), radius=n(48), outline=theme["glow1"], width=n(2))
    rd.arc(box((11, 11, 245, 245)), 210, 48, fill=theme["glow2"], width=n(3))
    image = Image.alpha_composite(image, rim.filter(ImageFilter.GaussianBlur(n(8))))
    image = Image.alpha_composite(image, rim)
    glass_rim = Image.new("RGBA", image.size)
    gd = ImageDraw.Draw(glass_rim)
    gd.arc(box((17, 17, 239, 239)), 190, 322, fill=(235, 250, 255, 180), width=n(1.2))
    gd.arc(box((17, 17, 239, 239)), 326, 72, fill=(245, 220, 255, 115), width=n(1.2))
    image = Image.alpha_composite(image, glass_rim)

    mark_points = [(88, 61), (101, 49), (155, 49), (168, 61), (168, 198), (128, 161), (88, 198)]
    mark_points = [(n(x), n(y)) for x, y in mark_points]
    mark_mask = Image.new("L", image.size)
    md = ImageDraw.Draw(mark_mask)
    md.polygon(mark_points, fill=255)
    md.rounded_rectangle(box((88, 49, 168, 92)), radius=n(14), fill=255)

    # The bookmark gets its own colored aura and a dark drop shadow for depth.
    shadow_mask = Image.new("L", image.size)
    shadow_mask.paste(mark_mask, (0, n(6)))
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 185))
    shadow.putalpha(shadow_mask.filter(ImageFilter.GaussianBlur(n(10))))
    image = Image.alpha_composite(image, shadow)

    mark_halo = Image.new("RGBA", image.size, theme["glow1"])
    mark_halo.putalpha(mark_mask.filter(ImageFilter.GaussianBlur(n(12))).point(lambda p: p * 115 // 255))
    image = Image.alpha_composite(image, mark_halo)

    mark = gradient(image.size, theme["mark"])
    mark.putalpha(mark_mask)
    image = Image.alpha_composite(image, mark)

    # Bright edge rails and a translucent glass highlight restore the old 3-D feel.
    outline = Image.new("RGBA", image.size)
    od = ImageDraw.Draw(outline)
    od.line(mark_points + [mark_points[0]], fill=(226, 249, 255, 235), width=n(2), joint="curve")
    od.line(mark_points[3:6], fill=theme["glow2"], width=n(2), joint="curve")
    image = Image.alpha_composite(image, outline.filter(ImageFilter.GaussianBlur(n(4))))
    image = Image.alpha_composite(image, outline)

    shine_mask = Image.new("L", image.size)
    sd = ImageDraw.Draw(shine_mask)
    sd.polygon(
        [(n(96), n(61)), (n(157), n(56)), (n(150), n(103)), (n(98), n(128))],
        fill=120,
    )
    shine_mask = ImageChops.multiply(shine_mask.filter(ImageFilter.GaussianBlur(n(3))), mark_mask)
    shine = Image.new("RGBA", image.size, (255, 255, 255, 0))
    shine.putalpha(shine_mask)
    image = Image.alpha_composite(image, shine)

    accents = Image.new("RGBA", image.size)
    ad = ImageDraw.Draw(accents)
    ad.ellipse(box((187, 50, 190, 53)), fill=(255, 255, 255, 210))
    ad.ellipse(box((55, 179, 57, 181)), fill=theme["glow1"])
    image = Image.alpha_composite(image, accents.filter(ImageFilter.GaussianBlur(n(1))))

    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main():
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    for name, theme in THEMES.items():
        icon = paint(theme)
        path = ROOT / ("icon-%s.ico" % name)
        icon.save(path, format="ICO", sizes=sizes, bitmap_format="png")
        print(path, path.stat().st_size)
    (ROOT / "bookmark.ico").write_bytes((ROOT / "icon-aurora.ico").read_bytes())


if __name__ == "__main__":
    main()
