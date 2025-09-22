let startTime = null;
let timerInterval = null;


// Helpers 
function updateBackButtonState(state) {
  const backBtn = document.getElementById("back-link");
  if (!backBtn) return;

  const currentIndex = typeof state.current_index === "number"
    ? state.current_index
    : parseInt(state.current_index || "0", 10) || 0;
  const backRule = state.back_rule || "unlimited";
  const backUsed = Number(state.back_used || 0);
  const isAtStart = currentIndex <= 0;

  const shouldDisable = isAtStart || backRule === "disabled" || (backRule === "once" && backUsed >= 1);

  backBtn.classList.toggle("disabled", shouldDisable);
  backBtn.disabled = shouldDisable;
  backBtn.style.pointerEvents = shouldDisable ? "none" : "";
  backBtn.style.opacity = shouldDisable ? "0.6" : "";
}

// duration in ms
function showToast(message, duration = 3000) {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => toast.classList.add("show"), 10);

  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => container.removeChild(toast), 300);
  }, duration);
}


//  Start game 
document.getElementById("start-game")?.addEventListener("click", () => {
  const backRule = document.querySelector('[data-rule="back_rule"] .rule-option.active')?.dataset.value || "unlimited";
  const toc = document.querySelector('[data-rule="toc"] .rule-option.active')?.dataset.value || "off";
  const difficulty = document.querySelector('[data-rule="difficulty"] .rule-option.active')?.dataset.value || "hard";
  const peekRule = document.querySelector('[data-rule="peek_rule"] .rule-option.active')?.dataset.value || "on";

  const gameQuery = `back_rule=${encodeURIComponent(backRule)}&toc=${encodeURIComponent(toc)}&difficulty=${encodeURIComponent(difficulty)}&peek_rule=${encodeURIComponent(peekRule)}`;

  fetch(`/api/challenge?${gameQuery}`)
    .then(r => r.json())
    .then(data => window.location.href = `/wiki/${encodeURIComponent(data.start)}`)
    .catch(err => console.error("Failed to start game:", err));
});

document.getElementById("home-link")?.addEventListener("click", e => {
  e.preventDefault();
  window.location.href = "/";
});

document.getElementById("back-link")?.addEventListener("click", e => {
  e.preventDefault();
  window.location.href = "/back";
});


//  Share/ start friend game 
document.getElementById("share-link")?.addEventListener("click", async () => {
  const backRule = document.querySelector('[data-rule="back_rule"] .rule-option.active')?.dataset.value || "unlimited";
  const toc = document.querySelector('[data-rule="toc"] .rule-option.active')?.dataset.value || "off";
  const difficulty = document.querySelector('[data-rule="difficulty"] .rule-option.active')?.dataset.value || "hard";
  const peekRule = document.querySelector('[data-rule="peek_rule"] .rule-option.active')?.dataset.value || "on";

  const gameQuery = `back_rule=${encodeURIComponent(backRule)}&toc=${encodeURIComponent(toc)}&difficulty=${encodeURIComponent(difficulty)}&peek_rule=${encodeURIComponent(peekRule)}`;

  const res = await fetch(`/api/challenge/share?${gameQuery}`);
  const data = await res.json();
  const token = data.token;

  const shareUrl = `${window.location.origin}/share/${token}`;
  document.getElementById("share-popup").classList.remove("hidden");
  document.getElementById("share-start").dataset.token = token;

  try {
    await navigator.clipboard.writeText(shareUrl);
    const confirm = document.getElementById("copy-confirmation");
    confirm.classList.remove("hidden");
    setTimeout(() => confirm.classList.add("hidden"), 2000);
  } catch (err) {
    console.error("Failed to copy link:", err);
  }
});

document.getElementById("copy-link")?.addEventListener("click", async () => {
  const token = document.getElementById("share-start").dataset.token;
  const shareUrl = `${window.location.origin}/share/${token}`;
  const confirm = document.getElementById("copy-confirmation");

  try {
    await navigator.clipboard.writeText(shareUrl);
    confirm.classList.remove("hidden");
    setTimeout(() => confirm.classList.add("hidden"), 2000);
  } catch (err) {
    console.error("Failed to copy link:", err);
  }
});

document.getElementById("share-start")?.addEventListener("click", () => {
  const token = document.getElementById("share-start").dataset.token;
  if (token) window.location.href = `/share/${token}/start`;
});


//  Summary Dropdown 
const summaryButton = document.getElementById("summary-button");
const summaryDropdown = document.getElementById("summary-dropdown");

if (summaryButton && summaryDropdown) {
  summaryButton.addEventListener("click", e => {
    e.stopPropagation();
    summaryDropdown.classList.toggle("show");
  });

  document.addEventListener("click", e => {
    if (!summaryDropdown.contains(e.target) && e.target !== summaryButton) {
      summaryDropdown.classList.remove("show");
    }
  });
}



// Fetch and update game state 
async function updateState() {
  const response = await fetch("/api/state");
  const data = await response.json();

  updateBackButtonState(data);

  // Win pop up
  if (data.has_won && !window.hasAlerted) {
    window.hasAlerted = true;

    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }

    const articleEl = document.getElementById("win-article");
    const clicksEl = document.getElementById("win-clicks");
    const timeEl = document.getElementById("win-time");
    const pathEl = document.getElementById("win-path");

    const targetName = data.end.replace(/_/g, " ");
    const wikiUrl = `https://en.wikipedia.org/wiki/${data.end}`;

    articleEl.innerHTML = `Reached article: <a href="${wikiUrl}" target="_blank" rel="noopener noreferrer">${targetName}</a>`;
    clicksEl.textContent = `Articles visited: ${data.clicks}`;

    let totalSeconds = Math.floor(data.elapsed);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    timeEl.textContent = `Time: ${minutes}:${seconds.toString().padStart(2, "0")}`;

    if (pathEl) {
      pathEl.innerHTML = "";
      data.visited.forEach((title, idx) => {
        const li = document.createElement("li");
        li.textContent = `${idx + 1}. ${title.replace(/_/g, " ")}`;
        pathEl.appendChild(li);
      });
    }

    document.getElementById("win-popup").classList.remove("hidden");
    document.getElementById("win-home").addEventListener("click", () => {
      window.location.href = "/";
    });
  }

  // Disable back button if needed
  const backLink = document.getElementById("back-link");
  if (backLink) {
    const shouldDisable =
      data.back_rule === "disabled" ||
      (data.back_rule === "once" && data.back_used >= 1) ||
      data.current_index <= 0;

    backLink.classList.toggle("disabled", shouldDisable);
    backLink.style.pointerEvents = shouldDisable ? "none" : "auto";
    backLink.style.opacity = shouldDisable ? 0.5 : 1;
  }
}



async function initTimer() {
  const timerEl = document.getElementById("timer");
  if (!timerEl) return;

  // Fetch initial state from server
  let startTime = Date.now(); // fallback
  try {
    const res = await fetch("/api/state");
    if (res.ok) {
      const data = await res.json();
      // Compute approximate client startTime from server elapsed
      startTime = Date.now() - (data.elapsed * 1000);
    }
  } catch (err) {
    console.error("Failed to fetch initial game state for timer:", err);
  }

  const updateTimer = () => {
    let elapsed = Math.floor((Date.now() - startTime) / 1000);
    elapsed = Math.max(0, elapsed); // never negative

    if (elapsed < 60) {
      timerEl.innerText = `Time: ${elapsed}s`;
    } else {
      const minutes = Math.floor(elapsed / 60);
      const seconds = elapsed % 60;
      timerEl.innerText = `Time: ${minutes}:${seconds.toString().padStart(2, "0")}`;
    }
  };

  updateTimer(); // initial render
  timerInterval = setInterval(updateTimer, 1000);
}



document.addEventListener("DOMContentLoaded", () => {
  // rule selection
  document.querySelectorAll(".rule-group").forEach(group => {
    const options = group.querySelectorAll(".rule-option");
    options.forEach(opt => {
      opt.addEventListener("click", () => {
        options.forEach(o => o.classList.remove("active"));
        opt.classList.add("active");
      });
    });
  });

  initTimer();

  const tocSidebar = document.getElementById("toc-sidebar");
  if (tocSidebar) {
    document.body.classList.add("toc-enabled");
    tocSidebar.querySelectorAll("a").forEach(link => {
      link.addEventListener("click", e => {
        e.preventDefault();
        const targetId = link.getAttribute("href").substring(1);
        const targetEl = document.getElementById(targetId);
        if (targetEl) {
          window.scrollTo({ top: targetEl.offsetTop - 60, behavior: "smooth" });
        }
      });
    });
  }

  // rule persistence for home page
  document.querySelectorAll(".rule-group").forEach(group => {
    const groupName = group.dataset.rule;
    const savedValue = sessionStorage.getItem(`wiki-game-rule-${groupName}`);
    if (savedValue) {
      group.querySelectorAll(".rule-option").forEach(option => {
        option.classList.toggle("active", option.dataset.value === savedValue);
      });
    }
  });

  document.querySelectorAll(".rule-group .rule-option").forEach(option => {
    option.addEventListener("click", () => {
      const group = option.closest(".rule-group").dataset.rule;
      const value = option.dataset.value;
      sessionStorage.setItem(`wiki-game-rule-${group}`, value);
      option.parentElement.querySelectorAll(".rule-option").forEach(el => el.classList.remove("active"));
      option.classList.add("active");
    });
  });

  updateState();
});



// Peek Modal 
document.addEventListener("DOMContentLoaded", () => {
  const peekBtn = document.getElementById("peek-btn");
  const modal = document.getElementById("peekModal");
  const closeBtn = document.getElementById("peekClose");
  const peekContent = document.getElementById("peekContent");

  peekBtn?.addEventListener("click", async () => {
    const target = window.targetArticle;
    try {
      const res = await fetch(`/peek/${encodeURIComponent(target)}`);
      if (!res.ok) throw new Error(res.status);
      const html = await res.text();
      peekContent.innerHTML = html;

      peekContent.querySelectorAll("a").forEach(a => {
        if (!a.closest("#toc-sidebar")) {
          a.removeAttribute("href");
          a.style.pointerEvents = "none";
          a.style.color = "inherit";
          a.style.textDecoration = "none";
        }
      });

      peekContent.querySelectorAll("#toc-sidebar a").forEach(link => {
        link.addEventListener("click", e => {
          e.preventDefault();
          const targetId = link.getAttribute("href").substring(1);
          const targetEl = peekContent.querySelector(`#${targetId}`);
          if (targetEl) targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      });

      modal.style.display = "block";
      document.body.style.overflow = "hidden";
    } catch (err) {
      console.error("Failed to load peek article:", err);
      peekContent.innerHTML = `<p>Failed to load article.</p>`;
      modal.style.display = "block";
      document.body.style.overflow = "hidden";
    }
  });

  closeBtn?.addEventListener("click", () => {
    modal.style.display = "none";
    peekContent.innerHTML = "";
    document.body.style.overflow = "";
  });

  window.addEventListener("click", e => {
    if (e.target === modal) {
      modal.style.display = "none";
      peekContent.innerHTML = "";
      document.body.style.overflow = "";
    }
  });
});



// Global warnings
 
// Block invalid Wikipedia links
document.addEventListener("click", e => {
  const link = e.target.closest("a");
  if (!link) return;
  const href = link.getAttribute("href");
  if (!href) return;
  const fullUrl = new URL(href, window.location.origin);

  if (fullUrl.href.includes("$%#@!")) {
    e.preventDefault();
    showToast("⚠️ That’s not a valid Wikipedia article!");
    return false;
  }
});

// Block Ctrl/Cmd + F
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
    e.preventDefault();
    showToast("🚫 Searching is disabled for this game!");
  }
});