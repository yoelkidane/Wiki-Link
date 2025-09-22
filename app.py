import os, time, random, base64, json
from functools import lru_cache, wraps
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, render_template, session, jsonify, redirect, url_for, request


load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_only_key_change_me")
HEADERS = {"User-Agent": "WikiLink/2.0"}

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

WIKI_API_RANDOM = "https://en.wikipedia.org/api/rest_v1/page/random/summary"
WIKI_API_HTML = "https://en.wikipedia.org/api/rest_v1/page/html/{}"

with open("easy_articles.json", "r", encoding="utf-8") as f:
        EASY_ARTICLES = json.load(f)


@lru_cache(maxsize=256)
def fetch_html_cached(title):
    headers = HEADERS
    r = requests.get(WIKI_API_HTML.format(title), headers=headers, timeout=5)
    return r.text if r.status_code == 200 else None



#  Helpers 

def get_random_article():
    """Fetch a random Wikipedia article title + summary."""
    headers = HEADERS
    r = requests.get(WIKI_API_RANDOM, headers=headers)
    if r.status_code == 200:
        data = r.json()
        return {
            "title": data["title"].replace(" ", "_"),
            "summary": data.get("extract", "No summary available."),
        }
    return None

def get_random_easy_article():
    title = random.choice(EASY_ARTICLES)
    # Fetch summary like normal
    headers = HEADERS
    r = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}", headers=headers)
    if r.status_code == 200:
        data = r.json()
        return {"title": title, "summary": data.get("extract", "")}
    return {"title": title, "summary": ""}


def get_article_html(title):
    """
    Fetch REST-formatted HTML for a page, remove scripts/base tags, and
    rewrite all internal Wikipedia links so they point back into app
    as /wiki/<Article_Title>. Disable non-article links.
    """
    headers = HEADERS
    r = requests.get(WIKI_API_HTML.format(title), headers=headers)
    if r.status_code != 200:
        app.logger.debug(f"Failed to fetch HTML for {title}: {r.status_code}")
        return None

    soup = BeautifulSoup(r.text, "lxml")

    for t in soup.select("script, iframe, noscript, base, link[href], sup.reference, a[href^='#cite_note']"):
        t.decompose()

    # remove References section
    for header in soup.find_all(['h2', 'h3']):
        if header.get_text().strip().lower() == "references":
            header.decompose()
            next_node = header.find_next_sibling()
            while next_node and next_node.name not in ['h2', 'h3']:
                temp = next_node.find_next_sibling()
                next_node.decompose()
                next_node = temp

    # remove any divs/ol with class "reflist" or "references"
    for ref_list in soup.find_all(["div", "ol"], class_=["reflist", "references"]):
        ref_list.decompose()

    # Remove inline event handlers and potentially dangerous attributes from all tags
    for tag in soup.find_all(True):
        attrs = dict(tag.attrs)
        for attr in list(attrs.keys()):
            if attr.startswith("on"):  # onclick, onmouseover, etc
                del tag.attrs[attr]
            if "target" in tag.attrs:
                del tag.attrs["target"]
            if "rel" in tag.attrs:
                del tag.attrs["rel"]
            if "src" in tag.attrs and tag.name != "img":
                del tag.attrs["src"]
        for attr in [a for a in tag.attrs if a.startswith("data-")]:
            del tag.attrs[attr]

    # rewrite anchors to point back to the app
    for a in soup.find_all("a", href=True):
        href = a["href"]
        article = None

        if href.startswith("./"):
            article = href[2:]
        elif href.startswith("/wiki/"):
            article = href.split("/wiki/", 1)[1]
        elif href.startswith("//") and "wikipedia.org/wiki/" in href:
            article = href.split("/wiki/", 1)[1]
        elif href.startswith("http") and "wikipedia.org/wiki/" in href:
            article = href.split("/wiki/", 1)[1]
        elif href.startswith("/w/index.php"):
            parsed = urlparse(href)
            q = parse_qs(parsed.query)
            if "title" in q and q["title"]:
                article = q["title"][0]
        elif href.startswith("#"):
            a["href"] = href
            continue

        if article:
            article = article.split("#", 1)[0].split("?", 1)[0].strip()
            invalid_prefixes = ("Special:", "File:", "Category:", "Help:", "Talk:", "Template:", "Portal:")
            if not article or article == "Main_Page" or article.startswith(invalid_prefixes):
                a["href"] = "$%#@!"  # disable link to non-article pages
            else:
                a["href"] = f"/wiki/{article}"
        else:
            a["href"] = "$%#@!"

    # Table of contents building
    toc = []
    for h2 in soup.find_all("h2"):
        toc_title = h2.get_text(strip=True)
        toc_id = toc_title.replace(" ", "_").replace("\n", "")
        h2["id"] = toc_id
        toc.append({"id": toc_id, "title": toc_title})

    return str(soup), toc


def decode_state(encoded):
    """Decode base64 back into (start_title, end_title, and set of rules."""
    payload = base64.urlsafe_b64decode(encoded.encode()).decode()
    data = json.loads(payload)
    return (
        data["start"],
        data["end"],
        data.get("back_rule", "unlimited"),
        data.get("toc", "off"),
        data.get("difficulty", "hard"),
        data.get("peek_rule", "on")
    )


def get_article_summary(title):
    """Fetch summary for a given Wikipedia article."""
    headers = HEADERS
    try:
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
            headers=headers,
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("extract", "")
    except Exception:
        pass
    return ""


#  Routes

@app.route("/")
def home():
    session.clear()
    return render_template("index.html")


@app.route("/api/challenge")
def challenge():
    """Start a new game with random start & end articles."""

    # get rules from user selection (query params)
    back_rule = request.args.get("back_rule", "unlimited")
    toc = request.args.get("toc", "off")
    difficulty = request.args.get("difficulty", "hard") 
    peek_rule = request.args.get("peek_rule", "on")

    if difficulty == "easy":
        start = get_random_easy_article()
        end = get_random_easy_article()
        while end["title"] == start["title"]:
            end = get_random_easy_article()
    else:
        start = get_random_article()
        end = get_random_article()
        while end["title"] == start["title"]:
            end = get_random_article()

    session["start_page"] = start["title"]
    session["end_page"] = end["title"]
    session["end_summary"] = end["summary"]


    session["start_time"] = None
    session["clicks"] = 0
    session["visited"] = []
    session["current_index"] = 0

    # Rules
    session["back_rule"] = back_rule
    session["back_used"] = 0
    session["toc"] = toc
    session ["difficulty"] = difficulty
    session["peek_rule"] = peek_rule  

    return jsonify({
        "start": start["title"],
        "end": end["title"],
        "summary_end": end["summary"],
        "back_rule": back_rule,
        "toc": toc,
        "difficulty": difficulty,
        "peek_rule": peek_rule
    })


@app.route("/wiki/<title>")
def wiki_page(title):
    """Render a Wikipedia article inside the game. Manages session state (list of pages, clicks, win con.)."""
    html_content, toc = get_article_html(title)
    if not html_content:
        return f"Could not load Wikipedia article: {title}", 404

    # start timer on page 1
    if session.get("start_time") is None:
        session["start_time"] = time.time()

    visited = session.get("visited", [])
    current_index = session.get("current_index", -1)
    is_new_page = False

    if not visited:
        visited = [title]
        current_index = 0
        is_new_page = True
    else:
        if current_index < len(visited) - 1:
            visited = visited[:current_index + 1]

        if visited[current_index] != title:
            visited.append(title)
            current_index = len(visited) - 1
            is_new_page = True

    session["visited"] = visited
    session["current_index"] = current_index

    if is_new_page:
        session["clicks"] = session.get("clicks", 0) + 1

    disable_back = current_index <= 0 # if on first page, back is disabled

    # check win condition on page load
    win_check = (visited[-1] == session.get("end_page"))

    return render_template(
        "wiki_page.html",
        title=title,
        content=html_content,
        toc=toc,
        clicks=session.get("clicks", 0),
        target=session.get("end_page"),
        target_summary=session.get("end_summary"),
        has_won=win_check,
        disable_back=disable_back,
        peek_rule = session.get("peek_rule", "on")
    )


@app.route("/back")
def go_back():
    """Go back to the previous page in stack."""
    visited = session.get("visited", [])
    current_index = session.get("current_index", 0)
    back_rule = session.get("back_rule", "unlimited")
    back_used = session.get("back_used", 0)

    if not visited or current_index <= 0:
        return redirect(url_for("home"))

    if back_rule == "disabled":
        return redirect(url_for("wiki_page", title=visited[current_index]))
    if back_rule == "once" and back_used >= 1:
        return redirect(url_for("wiki_page", title=visited[current_index]))

    current_index -= 1
    session["current_index"] = current_index
    session["clicks"] = session.get("clicks", 0) + 1

    if back_rule == "once":
        session["back_used"] = back_used + 1

    prev_page = visited[current_index]
    return redirect(url_for("wiki_page", title=prev_page))


@app.route("/peek/<title>")
def peek_page(title):
    """
    Render a full Wikipedia article for the Peek modal.
    Reuses wiki_page.html, but sets peek_mode=True to hide UI.
    """
    html_content, toc = get_article_html(title)
    if not html_content:
        return f"Could not load Wikipedia article: {title}", 404

    return render_template(
        "wiki_page.html",
        title=title,
        content=html_content,
        toc=toc,
        clicks=0,
        target=session.get("end_page"),
        target_summary=session.get("end_summary"),
        peek_rule=session.get("peek_rule", "on"),
        peek_mode=True  # flag for template to disable game UI
    )

@app.route("/api/wiki/<title>")
def api_wiki_page(title):
    """Article HTML grab for peek."""
    html_content, toc = get_article_html(title)
    if not html_content:
        return jsonify({"error": "Could not fetch article"}), 404
    return jsonify({"content": html_content})


@app.route("/api/state")
def state():
    """State management endpoint for client-side UI."""
    visited = session.get("visited", [])
    end_page = session.get("end_page")

    has_won = visited and visited[-1] == end_page

    # important session keys for client-side UI
    current_index = session.get("current_index", 0)
    back_rule = session.get("back_rule", "unlimited")
    back_used = session.get("back_used", 0)
    toc = session.get("toc", "off")
    difficulty = session.get("difficulty", "hard")
    peek_rule = session.get("peek_rule", "on")


    if has_won and not session.get("win_announced", False):
        session["win_announced"] = True

    return jsonify({
        "start": session.get("start_page"),
        "end": end_page,
        "visited": visited,
        "clicks": session.get("clicks", 0),
        "elapsed": time.time() - session.get("start_time", time.time()),
        "has_won": has_won,
        "win_announced": session.get("win_announced", False),
        "current_index": current_index,
        "back_rule": back_rule,
        "back_used": back_used,
        "toc": toc,
        "difficulty": difficulty,
        "peek_rule": peek_rule
    })


# Share link (base64)

@app.route('/api/challenge/share')
def generate_share_challenge():

    difficulty = request.args.get("difficulty", "hard")

    if difficulty == "easy":
        start = get_random_easy_article()
        end = get_random_easy_article()
        while end["title"] == start["title"]:
            end = get_random_easy_article()
    else:
        start = get_random_article()
        end = get_random_article()
        while end["title"] == start["title"]:
            end = get_random_article()

    # Get rules from query params (from the home page)
    back_rule = request.args.get("back_rule", "unlimited")
    toc = request.args.get("toc", "off")
    peek_rule = request.args.get("peek_rule", "on")


    payload = json.dumps({
        "start": start["title"],
        "end": end["title"],
        "back_rule": back_rule,
        "toc": toc,
        "difficulty": difficulty,
        "peek_rule": peek_rule
    })
    token = base64.urlsafe_b64encode(payload.encode()).decode()

    link = url_for('friend_index', token=token, _external=True)
    return jsonify({"start": start, "end": end, "link": link, "token": token})


@app.route('/share/<token>')
def friend_index(token):
    """Landing page for a shared game link. Decodes the token and shows start/end articles."""
    try:
        payload = base64.urlsafe_b64decode(token.encode()).decode()
        data = json.loads(payload)
        start = data["start"]
        end = data["end"]
        back_rule = data.get("back_rule", "unlimited") 
        toc = data.get("toc", "off") 
        difficulty = data.get("difficulty", "hard")  
        peek_rule = data.get("peek_rule", "on")
    except Exception:
        return "Invalid or corrupted link", 400

    # Pass token and rules to template
    return render_template("friend_index.html", start=start, end=end, token=token, back_rule=back_rule, toc=toc, difficulty=difficulty, peek_rule=peek_rule)


@app.route("/share/<token>/start")
def share_start(token):
    """Start a shared game for a visitor who opened a /share/<token> link."""
    start, end, back_rule, toc, difficulty, peek_rule = decode_state(token)

    session['start_page'] = start
    session['end_page'] = end
    session['end_summary'] = get_article_summary(end)
    session['clicks'] = 0
    session['visited'] = []
    session['current_index'] = 0
    session['start_time'] = None

    session['back_rule'] = back_rule
    session['back_used'] = 0  
    session['toc'] = toc
    session['difficulty'] = difficulty
    session['peek_rule'] = peek_rule

    return redirect(url_for("wiki_page", title=start))

# Debugging 
if app.debug:
    @app.route("/debug")
    def debug():
        """Debug endpoint to view session state."""
        return jsonify({
            "back_rule": session.get("back_rule"),
            "back_used": session.get("back_used"),
            "toc": session.get("toc"),
            "difficulty": session.get("difficulty"),
            "visited": session.get("visited"),
            "current_index": session.get("current_index"),
            "peek_rule": session.get("peek_rule")
        })


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=int(os.environ.get("PORT", 5000))) 
