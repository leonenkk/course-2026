"""Мини-набор примитивов для диаграмм пояснительной записки (matplotlib).

Единицы измерения на холсте --- сантиметры итогового рисунка, поэтому размер
шрифта в пунктах совпадает с размером в готовом документе.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch, Polygon

plt.rcParams.update(
    {
        "font.family": "Liberation Serif",
        "font.size": 9.5,
        "axes.unicode_minus": False,
        "mathtext.fontset": "stix",
    }
)
CM = 1 / 2.54

# Стили: символьные компоненты, нейробионические, внешние, хранилища.
SYM = dict(fc="#dbe7f5", ec="#1f3a5f")
NEU = dict(fc="#fde3c4", ec="#8a4b08")
EXT = dict(fc="#ededed", ec="#444444")
STO = dict(fc="#e0f0dc", ec="#2f5d2a")
WHITE = dict(fc="#ffffff", ec="#222222")


class Canvas:
    def __init__(self, w, h, y0=0.0):
        self.w, self.h = w, h
        self.fig = plt.figure(figsize=(w * CM, h * CM))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(y0, y0 + h)
        self.ax.axis("off")

    # --- фигуры -----------------------------------------------------------
    def box(self, cx, cy, w, h, text="", style=SYM, ls="-", fs=9.5, bold=False,
            sub=None, rounded=0.18, lw=1.0, z=2, fs_sub=None, italic=False):
        p = FancyBboxPatch(
            (cx - w / 2, cy - h / 2), w, h,
            boxstyle=f"round,pad=0,rounding_size={rounded}",
            fc=style["fc"], ec=style["ec"], lw=lw, ls=ls, zorder=z,
        )
        self.ax.add_patch(p)
        fs_sub = fs_sub or fs - 1.5
        if sub:
            self.ax.text(cx, cy + h * 0.2, text, ha="center", va="center", fontsize=fs,
                         fontweight="bold" if bold else "normal", zorder=z + 1,
                         fontstyle="italic" if italic else "normal")
            self.ax.text(cx, cy - h * 0.21, sub, ha="center", va="center", fontsize=fs_sub,
                         color="#333333", zorder=z + 1, linespacing=1.05)
        else:
            self.ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
                         fontweight="bold" if bold else "normal", zorder=z + 1,
                         linespacing=1.1, fontstyle="italic" if italic else "normal")
        return (cx, cy, w, h)

    def rect(self, x0, y0, x1, y1, style=WHITE, ls="-", lw=1.0, z=1, fc=None):
        p = FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=0.2",
                           fc=fc if fc else style["fc"], ec=style["ec"], lw=lw, ls=ls, zorder=z)
        self.ax.add_patch(p)

    def ellipse(self, cx, cy, w, h, text, style=WHITE, fs=9, z=2):
        self.ax.add_patch(Ellipse((cx, cy), w, h, fc=style["fc"], ec=style["ec"], lw=1.0, zorder=z))
        self.ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, zorder=z + 1, linespacing=1.1)

    def diamond(self, cx, cy, w, h, text, style=WHITE, fs=8.5, z=2):
        pts = [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)]
        self.ax.add_patch(Polygon(pts, closed=True, fc=style["fc"], ec=style["ec"], lw=1.0, zorder=z))
        self.ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, zorder=z + 1, linespacing=1.05)

    def terminator(self, cx, cy, w, h, text, style=WHITE, fs=9):
        self.box(cx, cy, w, h, text, style=style, fs=fs, rounded=h / 2)

    def text(self, x, y, s, fs=8.5, ha="center", va="center", italic=False, color="black",
             bold=False, bg=True, z=6, rot=0):
        bbox = dict(fc="white", ec="none", pad=0.6, alpha=0.95) if bg else None
        self.ax.text(x, y, s, ha=ha, va=va, fontsize=fs, fontstyle="italic" if italic else "normal",
                     fontweight="bold" if bold else "normal", color=color, bbox=bbox, zorder=z,
                     linespacing=1.05, rotation=rot)

    def actor(self, x, y, label, fs=9):
        a = self.ax
        a.add_patch(plt.Circle((x, y + 0.75), 0.22, fc="white", ec="black", lw=1.0, zorder=3))
        a.plot([x, x], [y + 0.53, y - 0.1], c="black", lw=1.0, zorder=3)
        a.plot([x - 0.38, x + 0.38], [y + 0.35, y + 0.35], c="black", lw=1.0, zorder=3)
        a.plot([x, x - 0.33], [y - 0.1, y - 0.65], c="black", lw=1.0, zorder=3)
        a.plot([x, x + 0.33], [y - 0.1, y - 0.65], c="black", lw=1.0, zorder=3)
        a.text(x, y - 1.05, label, ha="center", va="top", fontsize=fs, linespacing=1.05)

    # --- линии ------------------------------------------------------------
    def line(self, pts, arrow=True, ls="-", lw=1.0, color="black", head=9, z=4, both=False):
        xs, ys = zip(*pts)
        if arrow and len(pts) > 2:
            self.ax.plot(xs[:-1], ys[:-1], c=color, lw=lw, ls=ls, zorder=z, solid_capstyle="butt")
            pts = pts[-2:]
        elif not arrow:
            self.ax.plot(xs, ys, c=color, lw=lw, ls=ls, zorder=z)
            return
        self.ax.annotate(
            "", xy=pts[-1], xytext=pts[0],
            arrowprops=dict(arrowstyle="<|-|>" if both else "-|>", lw=lw, color=color, ls=ls,
                            shrinkA=0, shrinkB=0, mutation_scale=head),
            zorder=z,
        )

    def marker(self, x, y, label, fs=7.2, r=0.27):
        self.ax.add_patch(plt.Circle((x, y), r, fc="white", ec="black", lw=0.9, zorder=8))
        self.ax.text(x, y, label, ha="center", va="center", fontsize=fs, fontweight="bold", zorder=9)

    def save(self, path, dpi=220):
        self.fig.savefig(path, dpi=dpi, facecolor="white")
        plt.close(self.fig)
