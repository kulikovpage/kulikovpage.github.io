#!/usr/bin/env python3
"""Builds the site into dist/. Python 3.9+, standard library only, so GitHub Actions needs no installs.

content/site.json             home page texts, site address and contact email (/admin → Site settings)
content/projects/<slug>.json  one file per project with every language inside (/admin → Projects)
public/                       copied as is: the admin panel, uploaded images, CSS, JS, icons

Run `python3 build.py`, then open dist/ with any static server.
"""
import hashlib
import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
DEFAULT = "en"
LOCALES = ["en", "uk", "ru", "pl", "es", "fr", "pt"]
LANG_NAMES = {"en": "English", "uk": "Українська", "ru": "Русский", "pl": "Polski",
              "es": "Español", "fr": "Français", "pt": "Português"}

# Interface words on project pages. A language missing here falls back to English.
UI = {
    "en": dict(skip="Skip to content", back="All projects", about="About", features="Features", help="Help & FAQ", contact="Contact",
               contact_text="Questions, ideas or found a bug? Write to us, we read every message.",
               privacy="Privacy Policy", updated="Updated {date}", soon="Coming soon to the App Store",
               beta="In beta", store="View on the App Store", testflight="Join the beta",
               screens="Screenshots", language="Language", prev="Previous", next="Next",
               shot="Screenshot {n} of {total}"),
    "uk": dict(skip="Перейти до змісту", back="Усі проєкти", about="Про застосунок", features="Можливості", help="Допомога й запитання",
               contact="Зв'язок", contact_text="Запитання, ідеї чи знайшли помилку? Напишіть нам, ми читаємо кожен лист.",
               privacy="Політика конфіденційності", updated="Оновлено {date}", soon="Незабаром в App Store",
               beta="Бета-версія", store="Відкрити в App Store", testflight="Долучитися до бети",
               screens="Знімки екрана", language="Мова", prev="Назад", next="Далі",
               shot="Знімок екрана {n} з {total}"),
    "ru": dict(skip="Перейти к содержимому", back="Все проекты", about="О приложении", features="Возможности", help="Помощь и вопросы",
               contact="Связь", contact_text="Вопросы, идеи или нашли ошибку? Напишите нам, мы читаем каждое письмо.",
               privacy="Политика конфиденциальности", updated="Обновлено {date}", soon="Скоро в App Store",
               beta="Бета-версия", store="Открыть в App Store", testflight="Присоединиться к бете",
               screens="Снимки экрана", language="Язык", prev="Назад", next="Дальше",
               shot="Снимок экрана {n} из {total}"),
    "pl": dict(skip="Przejdź do treści", back="Wszystkie projekty", about="O aplikacji", features="Funkcje", help="Pomoc i pytania",
               contact="Kontakt", contact_text="Pytania, pomysły albo znaleziony błąd? Napisz do nas, czytamy każdą wiadomość.",
               privacy="Polityka prywatności", updated="Zaktualizowano {date}", soon="Wkrótce w App Store",
               beta="Wersja beta", store="Zobacz w App Store", testflight="Dołącz do bety",
               screens="Zrzuty ekranu", language="Język", prev="Wstecz", next="Dalej",
               shot="Zrzut ekranu {n} z {total}"),
    "es": dict(skip="Saltar al contenido", back="Todos los proyectos", about="Acerca de", features="Funciones", help="Ayuda y preguntas",
               contact="Contacto", contact_text="¿Preguntas, ideas o has encontrado un error? Escríbenos, leemos todos los mensajes.",
               privacy="Política de privacidad", updated="Actualizada el {date}", soon="Muy pronto en el App Store",
               beta="En beta", store="Ver en el App Store", testflight="Únete a la beta",
               screens="Capturas de pantalla", language="Idioma", prev="Anterior", next="Siguiente",
               shot="Captura {n} de {total}"),
    "fr": dict(skip="Aller au contenu", back="Tous les projets", about="À propos", features="Fonctionnalités", help="Aide et questions",
               contact="Contact", contact_text="Des questions, des idées ou un bug ? Écrivez-nous, nous lisons chaque message.",
               privacy="Politique de confidentialité", updated="Mise à jour le {date}", soon="Bientôt sur l'App Store",
               beta="En bêta", store="Voir sur l'App Store", testflight="Rejoindre la bêta",
               screens="Captures d'écran", language="Langue", prev="Précédent", next="Suivant",
               shot="Capture {n} sur {total}"),
    "pt": dict(skip="Pular para o conteúdo", back="Todos os projetos", about="Sobre", features="Recursos", help="Ajuda e perguntas",
               contact="Contato", contact_text="Dúvidas, ideias ou encontrou um erro? Escreva para nós, lemos todas as mensagens.",
               privacy="Política de privacidade", updated="Atualizada em {date}", soon="Em breve na App Store",
               beta="Em beta", store="Ver na App Store", testflight="Participar do beta",
               screens="Capturas de tela", language="Idioma", prev="Anterior", next="Próxima",
               shot="Captura {n} de {total}"),
}

MONTHS = {
    "en": "January February March April May June July August September October November December",
    "uk": "січня лютого березня квітня травня червня липня серпня вересня жовтня листопада грудня",
    "ru": "января февраля марта апреля мая июня июля августа сентября октября ноября декабря",
    "pl": "stycznia lutego marca kwietnia maja czerwca lipca sierpnia września października listopada grudnia",
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre",
    "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
    "pt": "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro",
}
DATE_FORMAT = {"en": "{m} {d}, {y}", "uk": "{d} {m} {y} р.", "ru": "{d} {m} {y} г.", "pl": "{d} {m} {y} r.",
               "es": "{d} de {m} de {y}", "fr": "{d} {m} {y}", "pt": "{d} de {m} de {y}"}

# The home page is in English only.
STATUS_HOME = {"available": "On the App Store", "soon": "Coming soon", "beta": "Beta"}


def esc(text):
    return html.escape(str(text or ""), quote=True)


def fmt_date(value, lang):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    if not m:
        return ""
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    months = MONTHS.get(lang, MONTHS["en"]).split()
    return DATE_FORMAT.get(lang, DATE_FORMAT["en"]).format(d=d, m=months[mo - 1], y=y)


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


def has_text(block):
    return isinstance(block, dict) and any(
        block.get(k) for k in ("subtitle", "description", "features", "help", "privacy"))


class Project:
    def __init__(self, path, data):
        self.slug = slugify(path.stem)
        if set(data) & set(LOCALES) and isinstance(data.get(DEFAULT), dict):
            self.locales = {k: v for k, v in data.items() if k in LOCALES and isinstance(v, dict)}
        else:  # a file saved without languages
            self.locales = {DEFAULT: data}
        base = self.locales[DEFAULT]
        self.base = base
        self.title = base.get("title") or path.stem
        self.color = base.get("color") or "#5B5FC7"
        self.on_color = contrast_text(self.color)
        self.icon = base.get("icon") or ""
        self.status = base.get("status") or "soon"
        self.platforms = base.get("platforms") or []
        if isinstance(self.platforms, str):
            self.platforms = [self.platforms]
        self.app_store_url = (base.get("app_store_url") or "").strip()
        self.testflight_url = (base.get("testflight_url") or "").strip()
        self.email = (base.get("support_email") or "").strip()
        self.hidden = bool(base.get("hidden"))
        try:
            self.order = float(base.get("order", 10))
        except (TypeError, ValueError):
            self.order = 10
        self.privacy_updated = base.get("privacy_updated") or ""
        self.langs = [DEFAULT] + [l for l in LOCALES if l != DEFAULT and has_text(self.locales.get(l))]

    def get(self, lang, key, default=""):
        """A translated value, or the English one when the translation is empty."""
        value = (self.locales.get(lang) or {}).get(key)
        if value in (None, "", [], {}):
            value = self.base.get(key)
        return default if value in (None, "", [], {}) else value

    def url(self, lang=DEFAULT, page=""):
        parts = ["", self.slug]
        if lang != DEFAULT:
            parts.append(lang)
        if page:
            parts.append(page)
        return "/".join(parts) + "/"


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
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return site.get("url", "").rstrip("/") + path


def layout(site, *, lang, title, description, body, path, alternates=None, image="", tint=None, base_attrs=""):
    alt_links = ""
    for code, href in (alternates or {}).items():
        alt_links += '<link rel="alternate" hreflang="%s" href="%s">\n' % (code, esc(absolute(site, href)))
    if alternates:
        alt_links += '<link rel="alternate" hreflang="x-default" href="%s">\n' % esc(absolute(site, alternates[DEFAULT]))
    style = ' style="--tint:%s;--on-tint:%s"' % (esc(tint[0]), esc(tint[1])) if tint else ""
    og_image = absolute(site, image)
    return """<!doctype html>
<html lang="{lang}"{base_attrs}{style}>
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
{alt_links}<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/site.css?v={css}">
<script>document.documentElement.classList.add("js")</script>
{lang_js}<script src="/assets/site.js?v={js}" defer></script>
</head>
<body>
<a class="skip" href="#main">{skip}</a>
{body}
</body>
</html>
""".format(lang=lang, base_attrs=base_attrs, style=style, title=esc(title), description=esc(description),
           url=esc(absolute(site, path)), alt_links=alt_links,
           og_image='<meta property="og:image" content="%s">\n' % esc(og_image) if og_image else "",
           css=asset_version("site.css"), js=asset_version("site.js"),
           lang_js='<script src="/assets/lang.js?v=%s"></script>\n' % asset_version("lang.js") if "data-langs" in base_attrs else "",
           skip=UI.get(lang, UI[DEFAULT])["skip"], body=body)


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
        cover = p.get(DEFAULT, "cover")
        media = ('<img class="card-cover" src="%s" alt="" loading="lazy" decoding="async">' % esc(cover) if cover
                 else '<img class="card-art" src="%s" alt="" loading="lazy">' % esc(p.icon) if p.icon else "")
        icon = '<img class="icon" src="%s" alt="" width="56" height="56" loading="lazy">' % esc(p.icon) if p.icon else ""
        cards.append("""<a class="card reveal" href="{url}" style="--tint:{color}">
  <div class="card-media">{media}</div>
  <div class="card-body">
    {icon}
    <div class="card-text">
      <h3>{title}</h3>
      <p>{subtitle}</p>
      {chips}
    </div>
    <span class="status status-{status}">{status_label}</span>
  </div>
</a>""".format(url=p.url(), color=esc(p.color), media=media, icon=icon, title=esc(p.title),
               subtitle=esc(p.get(DEFAULT, "subtitle")), chips=chips(p.platforms), status=esc(p.status),
               status_label=esc(STATUS_HOME.get(p.status, ""))))
    if not cards:
        cards.append('<p class="empty">Projects will appear here soon.</p>')
    glows = "".join(";--glow%d:%s" % (n + 1, esc(p.color)) for n, p in enumerate(projects[:3]))
    single = " grid-single" if len(projects) == 1 else ""
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
    <div class="grid{single}">
      {cards}
    </div>
  </section>
</main>
{footer}""".format(brand=brand(site), glows=glows.lstrip(";"),
                   contact='<a href="mailto:%s">Contact</a>' % esc(site["email"]) if site.get("email") else "",
                   headline=esc(site.get("headline")), intro=esc(site.get("intro")), single=single,
                   cards="\n      ".join(cards), footer=footer(site))
    return layout(site, lang=DEFAULT, title=site.get("name") or "Projects",
                  description=site.get("intro") or site.get("headline") or "", body=body, path="/",
                  image=projects[0].get(DEFAULT, "cover") if projects else "")


def lang_nav(project, lang, page, ui):
    if len(project.langs) < 2:
        return ""
    links = []
    for code in project.langs:
        current = ' aria-current="true"' if code == lang else ""
        links.append('<a href="%s" hreflang="%s" lang="%s" data-lang="%s" title="%s"%s>%s</a>' % (
            project.url(code, page), code, code, code, esc(LANG_NAMES[code]), current, code.upper()))
    items = "".join('<li><a href="%s" hreflang="%s" lang="%s" data-lang="%s"%s>%s</a></li>' % (
        project.url(code, page), code, code, code, ' aria-current="true"' if code == lang else "", esc(LANG_NAMES[code]))
        for code in project.langs)
    globe = ('<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><g fill="none" stroke="currentColor" '
             'stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9'
             'c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/></g></svg>')
    menu = '<details class="lang-menu"><summary aria-label="%s: %s">%s<span>%s</span></summary><ul>%s</ul></details>' % (
        esc(ui["language"]), esc(LANG_NAMES[lang]), globe, lang.upper(), items)
    return '<nav class="langs" aria-label="%s">%s</nav>%s' % (esc(ui["language"]), "".join(links), menu)


def lang_attrs(project, lang, page):
    return ' data-lang="%s" data-langs="%s" data-base="%s" data-page="%s"' % (
        lang, ",".join(project.langs), project.url(), page)


def project_page(site, project, lang):
    ui = UI.get(lang, UI[DEFAULT])
    p = project
    email = p.email or site.get("email") or ""
    if p.status == "available" and p.app_store_url:
        cta = '<a class="button" href="%s" rel="noopener">%s <span aria-hidden="true">↗</span></a>' % (
            esc(p.app_store_url), esc(ui["store"]))
    elif p.status == "beta" and p.testflight_url:
        cta = '<a class="button" href="%s" rel="noopener">%s <span aria-hidden="true">↗</span></a>' % (
            esc(p.testflight_url), esc(ui["testflight"]))
    else:
        cta = '<span class="pill">%s</span>' % esc(ui["beta"] if p.status == "beta" else ui["soon"])
    icon = ('<img class="p-icon" src="%s" alt="" width="112" height="112">' % esc(p.icon)) if p.icon else ""

    sections = []
    cover = p.get(lang, "cover")
    if cover:
        sections.append('<figure class="p-cover wrap reveal"><img src="%s" alt="" decoding="async"></figure>'
                        % esc(cover))
    shots = p.get(lang, "screenshots", [])
    if isinstance(shots, str):
        shots = [shots]
    shots = [s for s in shots if s]
    if shots:
        items = "".join(
            '<li><img src="%s" alt="%s" loading="%s" decoding="async"></li>'
            % (esc(s), esc(ui["shot"].format(n=n + 1, total=len(shots))), "eager" if n < 3 else "lazy")
            for n, s in enumerate(shots))
        sections.append("""<section class="shots reveal" aria-label="{label}">
  <ul class="shots-track" tabindex="0">{items}</ul>
  <div class="wrap shots-nav">
    <button type="button" class="round" data-shots="-1" aria-label="{prev}">←</button>
    <button type="button" class="round" data-shots="1" aria-label="{next}">→</button>
  </div>
</section>""".format(label=esc(ui["screens"]), items=items, prev=esc(ui["prev"]), next=esc(ui["next"])))
    description = p.get(lang, "description")
    if description:
        sections.append("""<section class="wrap split reveal">
  <h2>{title}</h2>
  <div class="prose">{text}</div>
</section>""".format(title=esc(ui["about"]), text=markdown(description)))
    features = [f for f in p.get(lang, "features", []) if isinstance(f, dict) and (f.get("title") or f.get("text"))]
    if features:
        cards = "".join("""<li class="feature reveal"><span class="feature-n">{n:02d}</span>
  <h3>{title}</h3><p>{text}</p></li>""".format(n=n + 1, title=esc(f.get("title")), text=esc(f.get("text")))
                        for n, f in enumerate(features))
        sections.append("""<section class="wrap block">
  <h2 class="reveal">{title}</h2>
  <ul class="features">{cards}</ul>
</section>""".format(title=esc(ui["features"]), cards=cards))
    help_items = [h for h in p.get(lang, "help", []) if isinstance(h, dict) and h.get("question")]
    if help_items:
        items = "".join("""<details class="faq-item"><summary>{q}</summary><div class="prose">{a}</div></details>"""
                        .format(q=esc(h.get("question")), a=markdown(h.get("answer"))) for h in help_items)
        sections.append("""<section id="help" class="wrap split reveal">
  <h2>{title}</h2>
  <div class="faq">{items}</div>
</section>""".format(title=esc(ui["help"]), items=items))
    if email:
        sections.append("""<section id="contact" class="wrap reveal">
  <div class="contact">
    <div><h2>{title}</h2><p>{text}</p></div>
    <a class="button button-quiet" href="mailto:{email}">{email}</a>
  </div>
</section>""".format(title=esc(ui["contact"]), text=esc(ui["contact_text"]), email=esc(email)))

    body = """<header class="top wrap">
  <a class="back" href="/"><span aria-hidden="true">←</span> {back}</a>
  {langs}
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
{footer}""".format(back=esc(ui["back"]), langs=lang_nav(p, lang, "", ui), icon=icon, title=esc(p.title),
                   subtitle=esc(p.get(lang, "subtitle")), cta=cta, chips=chips(p.platforms),
                   sections="\n  ".join(sections),
                   footer=footer(site, '<a href="%s">%s</a>' % (p.url(lang, "privacy"), esc(ui["privacy"]))))
    return layout(site, lang=lang, title="%s — %s" % (p.title, p.get(lang, "subtitle") or site.get("name", "")),
                  description=p.get(lang, "subtitle"), body=body, path=p.url(lang),
                  alternates={code: p.url(code) for code in p.langs} if len(p.langs) > 1 else None,
                  image=cover or p.icon, tint=(p.color, p.on_color), base_attrs=lang_attrs(p, lang, ""))


def privacy_page(site, project, lang):
    ui = UI.get(lang, UI[DEFAULT])
    p = project
    updated = fmt_date(p.privacy_updated, lang)
    text = p.get(lang, "privacy")
    body = """<header class="top wrap">
  <a class="back" href="{home}"><span aria-hidden="true">←</span> {title}</a>
  {langs}
</header>
<main id="main" class="wrap narrow doc">
  <h1>{privacy}</h1>
  <p class="doc-meta">{title}{updated}</p>
  <div class="prose">{text}</div>
</main>
{footer}""".format(home=p.url(lang), title=esc(p.title), langs=lang_nav(p, lang, "privacy", ui),
                   privacy=esc(ui["privacy"]), updated=(" · " + esc(ui["updated"].format(date=updated))) if updated else "",
                   text=markdown(text), footer=footer(site, '<a href="%s">%s</a>' % (p.url(lang), esc(p.title))))
    return layout(site, lang=lang, title="%s — %s" % (ui["privacy"], p.title),
                  description="%s — %s" % (ui["privacy"], p.title), body=body, path=p.url(lang, "privacy"),
                  alternates={code: p.url(code, "privacy") for code in p.langs} if len(p.langs) > 1 else None,
                  tint=(p.color, p.on_color), base_attrs=lang_attrs(p, lang, "privacy"))


def not_found(site):
    body = """<header class="top wrap">{brand}</header>
<main id="main" class="wrap narrow doc center">
  <h1>Page not found</h1>
  <p class="lead">The page may have moved. Everything is on the home page.</p>
  <p><a class="button" href="/">Go to the home page</a></p>
</main>
{footer}""".format(brand=brand(site), footer=footer(site))
    return layout(site, lang=DEFAULT, title="Page not found", description="", body=body, path="/404.html")


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
        for lang in p.langs:
            write(p.url(lang), project_page(site, p, lang))
            urls.append(p.url(lang))
            if p.get(lang, "privacy"):
                write(p.url(lang, "privacy"), privacy_page(site, p, lang))
                urls.append(p.url(lang, "privacy"))
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
