"""TriggerWord desktop splash.

Shows the intro animation as a frameless, transparent, always-on-top window
floating on the desktop while the app boots. Looney-Tunes style: the art
plays full-size inside a black iris that slowly closes over the animation,
ending as a small pupil around the carrot outro, then snaps shut to nothing.
"PART OF HOPZLE TOOLKIT" curves along the rim in the toolkit's cyan.

Launched hidden by the launchers in full mode. Exits silently if tkinter,
Pillow, or numpy are unavailable (e.g. a shared install) - the splash is
decoration, never a dependency.
"""
import math
import os
import sys

try:
    import tkinter as tk
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont, ImageSequence, ImageTk
except Exception:
    sys.exit(0)

GIF = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "static", "images", "triggerword_splash.gif")

MAGIC = "#fe00fe"          # color-key for window transparency
MAGIC_RGB = (254, 0, 254)
SPEED = 4                  # show every SPEED-th frame; with ~30ms decode per
                           # frame the full cycle lands around 3 seconds
FAILSAFE_MS = 15000

# Iris curve, baked from measured art extents:
#   f0-160   big logo on screen (radius ~235)      -> hold open at 245
#   f160-280 logo collapses, center drifts         -> glide to 150
#   f280-430 carrot outro (~90, hops to ~139)      -> ease to 120
INNER_R = 245              # opening radius; also sets the window size
CANVAS = 2 * (INNER_R + 2)

# Rim inscription (Hopzle toolkit brand: Poppins, cyan #16e0d2)
TEXT = "PART OF HOPZLE TOOLKIT"
TEXT_COLOR = (22, 224, 210)
FONT_SIZE = 15
TEXT_TRACKING = 2          # extra px between glyphs along the arc
TEXT_MIN_RADIUS = 70       # rim text disappears once the iris is this small

YY, XX = np.ogrid[:CANVAS, :CANVAS]
R2 = (XX - CANVAS / 2) ** 2 + (YY - CANVAS / 2) ** 2


def iris(i):
    """(radius, art-space center) of the iris for original frame i."""
    if i <= 160:
        return 245.0, (296.0, 209.0)
    if i <= 280:
        t = (i - 160) / 120
        return 245 - t * 95, (296 + t * 24, 209 + t * 19)
    if i <= 430:
        t = (i - 280) / 150
        return 150 - t * 30, (320.0, 228.0)
    return 120.0, (320.0, 228.0)


def load_font():
    for path in (r"C:\Windows\Fonts\Poppins-Bold.ttf",
                 os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\Poppins-Bold.ttf"),
                 r"C:\Windows\Fonts\arialbd.ttf"):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, FONT_SIZE)
            except Exception:
                pass
    return None


FONT = load_font()
_glyphs = {}
_text_layers = {}


def glyph(ch):
    if ch not in _glyphs:
        bbox = FONT.getbbox(ch)
        tile = Image.new("RGBA", (bbox[2] - bbox[0] + 4, bbox[3] - bbox[1] + 4), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((2 - bbox[0], 2 - bbox[1]), ch, font=FONT,
                                  fill=TEXT_COLOR + (255,))
        _glyphs[ch] = tile
    return _glyphs[ch]


def text_layer(radius):
    """RGBA layer with the inscription curved along the bottom rim, cached
    per integer radius (holds are free; the shrink builds each step once)."""
    key = int(radius)
    if key in _text_layers:
        return _text_layers[key]
    layer = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    c = CANVAS / 2
    r_text = radius - 12 - FONT_SIZE / 2
    advances = [FONT.getlength(ch) + TEXT_TRACKING for ch in TEXT]
    span = sum(advances) / r_text
    theta = math.pi / 2 + span / 2  # left end of the bottom arc
    for ch, adv in zip(TEXT, advances):
        dtheta = adv / r_text
        mid = theta - dtheta / 2
        if ch != " ":
            tile = glyph(ch).rotate(90 - math.degrees(mid), expand=True,
                                    resample=Image.BICUBIC)
            layer.alpha_composite(tile, (int(c + r_text * math.cos(mid) - tile.width / 2),
                                         int(c + r_text * math.sin(mid) - tile.height / 2)))
        theta -= dtheta
    _text_layers[key] = layer
    return layer


def frames():
    im = Image.open(GIF)
    w, h = im.size
    c = CANVAS / 2

    for i, frame in enumerate(ImageSequence.Iterator(im)):
        if i % SPEED:
            continue
        duration = frame.info.get("duration", 20)
        radius, (acx, acy) = iris(i)

        # The circle stays at the canvas center; the art shifts under it so
        # the iris tracks the artwork's drifting center. The gif frame is
        # larger than the canvas, so clip the paste region.
        x0, y0 = int(c - acx), int(c - acy)
        dx0, dy0 = max(0, x0), max(0, y0)
        dx1, dy1 = min(CANVAS, x0 + w), min(CANVAS, y0 + h)
        sx0, sy0 = dx0 - x0, dy0 - y0
        sx1, sy1 = sx0 + (dx1 - dx0), sy0 + (dy1 - dy0)

        canvas = np.zeros((CANVAS, CANVAS, 3), dtype=np.uint8)  # black disc fill
        canvas[dy0:dy1, dx0:dx1] = np.array(frame.convert("RGB"))[sy0:sy1, sx0:sx1]
        canvas[R2 > (radius + 1) ** 2] = MAGIC_RGB

        img = Image.fromarray(canvas)
        if FONT and radius > TEXT_MIN_RADIUS:
            layer = text_layer(radius)
            img.paste(layer, (0, 0), layer)
        yield img, duration


def main():
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=MAGIC)
    try:
        root.attributes("-transparentcolor", MAGIC)
    except tk.TclError:
        pass  # non-Windows: opaque splash is still fine

    gen = frames()
    try:
        first, _ = next(gen)
    except StopIteration:
        return
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{CANVAS}x{CANVAS}+{(sw - CANVAS) // 2}+{(sh - CANVAS) // 2}")

    label = tk.Label(root, bg=MAGIC, bd=0, highlightthickness=0)
    label.pack()
    photo = ImageTk.PhotoImage(first)
    label.configure(image=photo)
    label.image = photo
    state = {"last": first}

    def iris_close(radii=(100, 80, 62, 46, 32, 20, 10, 4)):
        # The classic ending: snap the iris shut to nothing, fast.
        if not radii:
            root.destroy()
            return
        arr = np.array(state["last"])
        arr[R2 > radii[0] ** 2] = MAGIC_RGB
        p = ImageTk.PhotoImage(Image.fromarray(arr))
        label.configure(image=p)
        label.image = p
        root.after(25, lambda: iris_close(radii[1:]))

    def advance():
        try:
            img, _ = next(gen)
        except StopIteration:
            iris_close()
            return
        state["last"] = img
        p = ImageTk.PhotoImage(img)
        label.configure(image=p)
        label.image = p
        root.after(10, advance)  # decode time dominates; run as fast as it can

    root.bind("<Button-1>", lambda e: root.destroy())  # click to skip
    root.after(10, advance)
    root.after(FAILSAFE_MS, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
