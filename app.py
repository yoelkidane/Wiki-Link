from flask import Flask, render_template, session, jsonify, redirect, url_for
import requests
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs


app = Flask(__name__)
app.secret_key = "replace_with_a_secure_random_key"

WIKI_API_RANDOM = "https://en.wikipedia.org/api/rest_v1/page/random/summary"
WIKI_API_HTML = "https://en.wikipedia.org/api/rest_v1/page/html/{}"


# ------------------ Helpers ------------------ #

def get_random_article():
    """Fetch a random Wikipedia article title + summary."""
    headers = {"User-Agent": "WikipediaGame/1.0 (https://example.com)"}
    r = requests.get(WIKI_API_RANDOM, headers=headers)
    if r.status_code == 200:
        data = r.json()
        return {
            "title": data["title"].replace(" ", "_"),
            "summary": data.get("extract", "No summary available."),
        }
    return None


def get_article_html(title):
    """
    Fetch REST-formatted HTML for a page, remove scripts/base tags,
    and rewrite internal Wikipedia links to point back to /wiki/<title>.
    """
    headers = {"User-Agent": "WikipediaGame/1.0 (https://example.com)"}
    r = requests.get(WIKI_API_HTML.format(title), headers=headers)
    if r.status_code != 200:
        app.logger.debug(f"Failed to fetch HTML for {title}: {r.status_code}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # Remove potentially dangerous or unnecessary elements
    for tagname in ("script", "iframe", "noscript"):
        for t in soup.find_all(tagname):
            t.decompose()

    for base in soup.find_all("base"):
        base.decompose()

    for link in soup.find_all("link", href=True):
        link.decompose()

    for sup in soup.find_all("sup", class_="reference"):
        sup.decompose()

    for a in soup.select("a[href^='#cite_note']"):
        a.decompose()

    # Remove References section
    for header in soup.find_all(['h2', 'h3']):
        if header.get_text().strip().lower() == "references":
            # Remove the header itself
            header.decompose()

            next_node = header.find_next_sibling()
            while next_node and next_node.name not in ['h2', 'h3']:
                temp = next_node.find_next_sibling()
                next_node.decompose()
                next_node = temp

    # Also remove any divs/ol with class "reflist" or "references"
    for ref_list in soup.find_all(["div", "ol"], class_=["reflist", "references"]):
        ref_list.decompose()

    # Remove inline event handlers and potentially dangerous attributes from all tags
    for tag in soup.find_all(True):
        attrs = dict(tag.attrs)
        for attr in list(attrs.keys()):
            if attr.startswith("on"): 
                del tag.attrs[attr]
        if "target" in tag.attrs:
            del tag.attrs["target"]
        if "rel" in tag.attrs:
            del tag.attrs["rel"]
        for attr in [a for a in tag.attrs if a.startswith("data-")]:
            del tag.attrs[attr]

    orig_links = [a["href"] for a in soup.find_all("a", href=True)[:200]]

    # Rewrite anchors 
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

        # Normalize + filter article if found
        if article:
            # remove fragment and query leftovers
            article = article.split("#", 1)[0].split("?", 1)[0].strip()

            invalid_prefixes = ("Special:", "File:", "Category:", "Help:", "Talk:", "Template:", "Portal:")
            if not article or article == "Main_Page" or article.startswith(invalid_prefixes):
                a["href"] = "#"
            else:
                a["href"] = f"/wiki/{article}"

        else:
            a["href"] = "#"

    # ---- Debug: log a sample of original vs rewritten links so we can inspect what happened ----
    try:
        rewritten = [a["href"] for a in soup.find_all("a", href=True)[:200]]
        app.logger.debug("ORIG_LINKS_SAMPLE: %s", orig_links[:40])
        app.logger.debug("REWRITTEN_LINKS_SAMPLE: %s", rewritten[:40])
    except Exception:
        pass

    return str(soup)




# ------------------ Routes ------------------ #

@app.route("/")
def home():
    session.clear()
    return render_template("index.html")


@app.route("/api/challenge")
def challenge():
    """Start a new game with random start & end articles."""
    start = get_random_article()
    end = get_random_article()

    while end and start and end["title"] == start["title"]:
        end = get_random_article()

    session["start_page"] = start["title"]
    session["end_page"] = end["title"]
    session["end_summary"] = end["summary"]

    session["start_time"] = None
    session["clicks"] = 0
    session["visited"] = []

    return jsonify({
        "start": start["title"],
        "end": end["title"],
        "summary_end": end["summary"]
    })


@app.route("/wiki/<title>")
def wiki_page(title):
    """Render a Wikipedia article inside the game."""
    html_content = get_article_html(title)
    if not html_content:
        return f"Could not load Wikipedia article: {title}", 404

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

    disable_back = current_index <= 0

    win_check = (visited[-1] == session.get("end_page"))

    return render_template(
        "wiki_page.html",
        title=title,
        content=html_content,
        clicks=session.get("clicks", 0),
        target=session.get("end_page"),
        target_summary=session.get("end_summary"),
        has_won=win_check,
        disable_back=disable_back
    )

@app.route("/back")
def go_back():
    visited = session.get("visited", [])
    current_index = session.get("current_index", 0)

    if not visited or current_index <= 0:
        return redirect(url_for("home"))

    current_index -= 1
    session["current_index"] = current_index
    session["clicks"] = session.get("clicks", 0) + 1 

    prev_page = visited[current_index]
    return redirect(url_for("wiki_page", title=prev_page))


@app.route("/api/state")
def state():
    """Debug endpoint to see current game state."""
    visited = session.get("visited", [])
    end_page = session.get("end_page")

    has_won = visited and visited[-1] == end_page

    if has_won and not session.get("win_announced", False):
        session["win_announced"] = True

    return jsonify({
        "start": session.get("start_page"),
        "end": end_page,
        "visited": visited,
        "clicks": session.get("clicks", 0),
        "elapsed": time.time() - session.get("start_time", time.time()),
        "has_won": has_won,
        "win_announced": session.get("win_announced", False)
    })

if __name__ == "__main__":
    app.run(debug=True)
