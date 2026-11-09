#!/usr/bin/env python3
"""Builds the site into dist/. Python 3.9+, standard library only, so GitHub Actions needs no installs.

content/site.json             home page texts, site address and contact email (/admin → Site settings)
content/projects/<slug>.json  one file per project (/admin → Projects)
public/                       copied as is: the admin panel, uploaded images, CSS, JS, icons

The site is in English only. Run `python3 build.py`, then open dist/ with any static server.
"""
import hashlib
import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
MONTHS = "January February March April May June July August September October November December".split()
STATUS = {"available": "On the App Store", "soon": "Coming soon", "beta": "Beta"}


def esc(text):
    return html.escape(str(text or ""), quote=True)


def fmt_date(value):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    return "%s %d, %s" % (MONTHS[int(m.group(2)) - 1], int(m.group(3)), m.group(1)) if m else ""


# ---------- Markdown (the subset the admin's editor writes) ----------

SAFE_URL = re.compile(r"^(https?:|mailto:|tel:|/|#)", re.I)


def inline(text):
    tokens = []

    def keep(fragment):
        tokens.append(fragment)
        return "\x00%d\x00" % (len(tokens) - 1)

    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!>~|])", lambda m: keep(esc(m.group(1))), text)
    text = re.sub(r"`([^`]+)`", lambda m: keep("<code>%s</code>" % esc(m.group(1))), text)
    text = re.sub(r"<(https?://[^>\s]+|mailto:[^>\s]+)>",
                  lambda m: keep('<a href="%s">%s</a>' % (esc(m.group(1)), esc(re.sub("^mailto:", "", m.group(1))))),
                  text)
    text = esc(text)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2)).strip()
        if not SAFE_URL.match(url):
            return label
        external = url.startswith("http")
        attrs = ' rel="noopener" target="_blank"' if external else ""
        return keep('<a href="%s"%s>%s</a>' % (esc(url), attrs, label))

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: "<strong>%s</strong>" % (m.group(1) or m.group(2)), text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", text)
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    text = re.sub(r"( {2,}|\\)\n", "<br>", text)
    text = text.replace("\n", " ")
    while "\x00" in text:
        text = re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m.group(1))], text)
    return text


def markdown(source):
    lines = str(source or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>%s</p>" % inline("\n".join(para)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        heading = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", stripped)
        bullet = re.match(r"^([-*+]|\d+[.)])\s+(.*)$", stripped)
        if not stripped:
            flush()
        elif heading:
            flush()
            level = min(max(len(heading.group(1)), 2), 4)
            out.append("<h%d>%s</h%d>" % (level, inline(heading.group(2)), level))
        elif re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flush()
            out.append("<hr>")
        elif stripped.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % markdown("\n".join(quote)))
            continue
        elif bullet:
            flush()
            ordered = bullet.group(1)[0].isdigit()
            items = []
            while i < len(lines):
                m = re.match(r"^\s*([-*+]|\d+[.)])\s+(.*)$", lines[i])
                if m:
                    items.append(m.group(2))
                elif lines[i].strip() and items and lines[i].startswith((" ", "\t")):
                    items[-1] += "\n" + lines[i].strip()
                else:
                    break
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(t) for t in items), tag))
            continue
        else:
            para.append(line)
        i += 1
    flush()
    return "\n".join(out)


# ---------- Content ----------

def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def contrast_text(hex_color):
    """Black or white, whichever reads better on the project colour (WCAG relative luminance)."""
    m = re.match(r"#?([0-9a-f]{6})", str(hex_color or ""), re.I)
    if not m:
        return "#ffffff"
    rgb = [int(m.group(1)[k:k + 2], 16) / 255 for k in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return "#111114" if (lum + 0.05) / 0.05 > 1.05 / (lum + 0.05) else "#ffffff"


class Project:
    def __init__(self, path, data):
        if isinstance(data.get("en"), dict):  # a file saved while the admin still had languages
            data = data["en"]
        self.data = data
        self.slug = slugify(path.stem)
        self.title = data.get("title") or path.stem
        self.subtitle = data.get("subtitle") or ""
        self.color = data.get("color") or "#5B5FC7"
        self.on_color = contrast_text(self.color)
        self.icon = data.get("icon") or ""
        self.cover = data.get("cover") or ""
        shots = data.get("screenshots") or []
        self.screenshots = [s for s in ([shots] if isinstance(shots, str) else shots) if s]
        self.description = data.get("description") or ""
        self.status = data.get("status") or "soon"
        platforms = data.get("platforms") or []
        self.platforms = [platforms] if isinstance(platforms, str) else platforms
        self.app_store_url = (data.get("app_store_url") or "").strip()
        self.testflight_url = (data.get("testflight_url") or "").strip()
        self.email = (data.get("support_email") or "").strip()
        self.privacy = data.get("privacy") or ""
        self.privacy_updated = data.get("privacy_updated") or ""
        self.hidden = bool(data.get("hidden"))
        try:
            self.order = float(data.get("order", 10))
        except (TypeError, ValueError):
            self.order = 10

    def url(self, page=""):
        return "/%s/%s" % (self.slug, page + "/" if page else "")


def load():
    site = json.loads((ROOT / "content" / "site.json").read_text("utf-8"))
    projects = []
    for path in sorted((ROOT / "content" / "projects").glob("*.json")):
        try:
            data = json.loads(path.read_text("utf-8"))
        except ValueError as error:
            raise SystemExit("%s: %s" % (path, error))
        project = Project(path, data)
        if not project.hidden:
            projects.append(project)
    projects.sort(key=lambda p: (p.order, p.title.lower()))
    return site, projects


# ---------- Pages ----------

def asset_version(name):
    return hashlib.sha1((ROOT / "public" / "assets" / name).read_bytes()).hexdigest()[:8]


def absolute(site, path):
    if not path or path.startswith("http"):
        return path or ""
    return site.get("url", "").rstrip("/") + path


def layout(site, *, title, description, body, path, image="", tint=None):
    style = ' style="--tint:%s;--on-tint:%s"' % (esc(tint[0]), esc(tint[1])) if tint else ""
    og_image = absolute(site, image)
    return """<!doctype html>
<html lang="en"{style}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="theme-color" content="#F6F5F1" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0E0E11" media="(prefers-color-scheme: dark)">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{url}">
{og_image}<link rel="canonical" href="{url}">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/site.css?v={css}">
<script>document.documentElement.classList.add("js")</script>
<script src="/assets/site.js?v={js}" defer></script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
{body}
</body>
</html>
""".format(style=style, title=esc(title), description=esc(description), url=esc(absolute(site, path)),
           og_image='<meta property="og:image" content="%s">\n' % esc(og_image) if og_image else "",
           css=asset_version("site.css"), js=asset_version("site.js"), body=body)


def brand(site):
    return '<a class="brand" href="/"><img class="brand-mark" src="/assets/favicon.svg" alt="" width="28" height="28">' \
           '<span>%s</span></a>' % esc(site.get("name") or "Projects")


def footer(site, extra=""):
    email = site.get("email") or ""
    mail = '<a href="mailto:%s">%s</a>' % (esc(email), esc(email)) if email else ""
    note = '<p class="foot-note">%s</p>' % esc(site["footer"]) if site.get("footer") else ""
    return """<footer class="foot">
  <div class="wrap foot-row">
    <p>© <span data-year>2026</span> {name}</p>
    <nav class="foot-links">{extra}{mail}</nav>
  </div>
  {note}
</footer>""".format(name=esc(site.get("name") or ""), extra=extra, mail=mail, note=note)


def chips(platforms):
    if not platforms:
        return ""
    return '<ul class="chips">%s</ul>' % "".join("<li>%s</li>" % esc(p) for p in platforms)


def home(site, projects):
    cards = []
    for p in projects:
        if p.cover:
            media = '<img class="card-cover" src="%s" alt="" decoding="async">' % esc(p.cover)
        elif p.icon:
            media = '<img class="card-art" src="%s" alt="" loading="lazy">' % esc(p.icon)
        else:
            media = ""
        icon = '<img class="icon" src="%s" alt="" width="48" height="48" loading="lazy">' % esc(p.icon) if p.icon else ""
        cards.append("""<a class="card reveal" href="{url}" style="--tint:{color}">
  <div class="card-media">{media}</div>
  <div class="card-body">
    {icon}
    <div class="card-text">
      <h3>{title}</h3>
      <p>{subtitle}</p>
    </div>
    <span class="status status-{status}">{status_label}</span>
  </div>
</a>""".format(url=p.url(), color=esc(p.color), media=media, icon=icon, title=esc(p.title),
               subtitle=esc(p.subtitle), status=esc(p.status), status_label=esc(STATUS.get(p.status, ""))))
    if not cards:
        cards.append('<p class="empty">Projects will appear here soon.</p>')
    glows = ";".join("--glow%d:%s" % (n + 1, esc(p.color)) for n, p in enumerate(projects[:3]))
    body = """<header class="top wrap">
  {brand}
  <nav class="top-links"><a href="#projects">Projects</a>{contact}</nav>
</header>
<main id="main">
  <section class="hero wrap" style="{glows}">
    <h1 class="reveal">{headline}</h1>
    <p class="lead reveal">{intro}</p>
  </section>
  <section id="projects" class="wrap projects" aria-labelledby="projects-title">
    <h2 id="projects-title" class="eyebrow">Projects</h2>
    <div class="grid">
      {cards}
    </div>
  </section>
</main>
{footer}""".format(brand=brand(site), glows=glows,
                   contact='<a href="mailto:%s">Contact</a>' % esc(site["email"]) if site.get("email") else "",
                   headline=esc(site.get("headline")), intro=esc(site.get("intro")),
                   cards="\n      ".join(cards), footer=footer(site))
    return layout(site, title=site.get("name") or "Projects", description=site.get("intro") or site.get("headline") or "",
                  body=body, path="/", image=projects[0].cover if projects else "")


def project_page(site, p):
    email = p.email or site.get("email") or ""
    if p.status == "available" and p.app_store_url:
        cta = '<a class="button" href="%s" rel="noopener">View on the App Store <span aria-hidden="true">↗</span></a>' \
              % esc(p.app_store_url)
    elif p.status == "beta" and p.testflight_url:
        cta = '<a class="button" href="%s" rel="noopener">Join the beta <span aria-hidden="true">↗</span></a>' \
              % esc(p.testflight_url)
    else:
        cta = '<span class="pill">%s</span>' % ("In beta" if p.status == "beta" else "Coming soon to the App Store")
    icon = '<img class="p-icon" src="%s" alt="" width="112" height="112">' % esc(p.icon) if p.icon else ""

    sections = []
    if p.cover:
        sections.append('<figure class="p-cover wrap reveal"><img src="%s" alt="" decoding="async"></figure>'
                        % esc(p.cover))
    if p.screenshots:
        items = "".join('<li><img src="%s" alt="Screenshot %d of %d" loading="%s" decoding="async"></li>'
                        % (esc(s), n + 1, len(p.screenshots), "eager" if n < 3 else "lazy")
                        for n, s in enumerate(p.screenshots))
        sections.append("""<section class="shots reveal" aria-label="Screenshots">
  <ul class="shots-track" tabindex="0">{items}</ul>
  <div class="wrap shots-nav">
    <button type="button" class="round" data-shots="-1" aria-label="Previous">←</button>
    <button type="button" class="round" data-shots="1" aria-label="Next">→</button>
  </div>
</section>""".format(items=items))
    if p.description:
        sections.append("""<section class="wrap split reveal">
  <h2>About</h2>
  <div class="prose">{text}</div>
</section>""".format(text=markdown(p.description)))
    if email:
        sections.append("""<section id="contact" class="wrap reveal">
  <div class="contact">
    <div><h2>Contact</h2><p>Questions, ideas or found a bug? Write to us, we read every message.</p></div>
    <a class="button button-quiet" href="mailto:{email}">{email}</a>
  </div>
</section>""".format(email=esc(email)))

    links = '<a href="%s">Privacy Policy</a>' % p.url("privacy") if p.privacy else ""
    body = """<header class="top wrap">
  <a class="back" href="/"><span aria-hidden="true">←</span> All projects</a>
</header>
<main id="main">
  <section class="p-hero wrap">
    {icon}
    <h1>{title}</h1>
    <p class="lead">{subtitle}</p>
    <div class="cta">{cta}{chips}</div>
  </section>
  {sections}
</main>
{footer}""".format(icon=icon, title=esc(p.title), subtitle=esc(p.subtitle), cta=cta, chips=chips(p.platforms),
                   sections="\n  ".join(sections), footer=footer(site, links))
    return layout(site, title="%s — %s" % (p.title, p.subtitle or site.get("name", "")), description=p.subtitle,
                  body=body, path=p.url(), image=p.cover or p.icon, tint=(p.color, p.on_color))


def privacy_page(site, p):
    updated = fmt_date(p.privacy_updated)
    body = """<header class="top wrap">
  <a class="back" href="{home}"><span aria-hidden="true">←</span> {title}</a>
</header>
<main id="main" class="wrap narrow doc">
  <h1>Privacy Policy</h1>
  <p class="doc-meta">{title}{updated}</p>
  <div class="prose">{text}</div>
</main>
{footer}""".format(home=p.url(), title=esc(p.title), updated=(" · Updated " + esc(updated)) if updated else "",
                   text=markdown(p.privacy), footer=footer(site, '<a href="%s">%s</a>' % (p.url(), esc(p.title))))
    return layout(site, title="Privacy Policy — %s" % p.title, description="Privacy Policy of %s" % p.title,
                  body=body, path=p.url("privacy"), tint=(p.color, p.on_color))


def not_found(site):
    body = """<header class="top wrap">{brand}</header>
<main id="main" class="wrap narrow doc center">
  <h1>Page not found</h1>
  <p class="lead">The page may have moved. Everything is on the home page.</p>
  <p><a class="button" href="/">Go to the home page</a></p>
</main>
{footer}""".format(brand=brand(site), footer=footer(site))
    return layout(site, title="Page not found", description="", body=body, path="/404.html")


def write(path, text):
    target = DIST / path.lstrip("/")
    if path.endswith("/"):
        target = target / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, "utf-8")


def main():
    site, projects = load()
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "public", DIST, ignore=shutil.ignore_patterns(".DS_Store"))
    write("/", home(site, projects))
    urls = ["/"]
    for p in projects:
        write(p.url(), project_page(site, p))
        urls.append(p.url())
        if p.privacy:
            write(p.url("privacy"), privacy_page(site, p))
            urls.append(p.url("privacy"))
    write("/404.html", not_found(site))
    base = site.get("url", "").rstrip("/")
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join("  <url><loc>%s</loc></url>\n" % esc(base + u) for u in urls) + "</urlset>\n", "utf-8")
    (DIST / "robots.txt").write_text("User-agent: *\nDisallow: /admin/\nSitemap: %s/sitemap.xml\n" % base, "utf-8")
    (DIST / ".nojekyll").write_text("", "utf-8")
    print("Built %d pages for %d project(s) into %s" % (len(urls) + 1, len(projects), DIST))


if __name__ == "__main__":
    main()
