let startTime = null;
let timerInterval = null;
    

// Start Game button (on index.html)
document.getElementById("start-game")?.addEventListener("click", () => {
  fetch("/api/challenge")
    .then((r) => r.json())
    .then((data) => {
      window.location.href = `/wiki/${encodeURIComponent(data.start)}`;
    });
});

// Timer
window.addEventListener("DOMContentLoaded", () => {
  const timerEl = document.getElementById("timer");
  const clicksEl = document.getElementById("click-counter");

  if (timerEl) {
    startTime = window.sessionStartTime
      ? new Date(window.sessionStartTime * 1000)
      : Date.now();

    // Function to format and update timer
    const updateTimer = () => {
      let elapsed = Math.floor((Date.now() - startTime) / 1000);
      if (elapsed < 60) {
        timerEl.innerText = `Time: ${elapsed}s`;
      } else {
        const minutes = Math.floor(elapsed / 60);
        const seconds = elapsed % 60;
        const paddedSeconds = seconds.toString().padStart(2, "0");
        timerEl.innerText = `Time: ${minutes}:${paddedSeconds}`;
      }
    };

    // Set initial timer immediately
    updateTimer();

    // Update timer every second
    timerInterval = setInterval(updateTimer, 1000);
  }
});

// Home link: restart game
document.getElementById("home-link")?.addEventListener("click", (e) => {
  e.preventDefault(); // Prevent default anchor jump
  window.location.href = "/"; // redirect to home page
});


const summaryButton = document.getElementById("summary-button");
const summaryDropdown = document.getElementById("summary-dropdown");

if (summaryButton && summaryDropdown) {
  summaryButton.addEventListener("click", (e) => {
    e.stopPropagation(); // prevent this click from triggering the document click
    summaryDropdown.classList.toggle("show"); // toggle visibility
  });

  // Close dropdown if clicking outside
  document.addEventListener("click", (e) => {
    if (!summaryDropdown.contains(e.target) && e.target !== summaryButton) {
      summaryDropdown.classList.remove("show");
    }
  });
}

document.getElementById("back-link")?.addEventListener("click", (e) => {
    e.preventDefault();
    window.location.href = "/back"; // browser follows the redirect
});

window.addEventListener("DOMContentLoaded", () => {
    updateState();
});

async function updateState() {
    const response = await fetch("/api/state");
    const data = await response.json();

    if (data.has_won && !window.hasAlerted) {
        window.hasAlerted = true; // make sure it only fires once

        // Stop timer on win
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }

        // Fill modal content
        const articleEl = document.getElementById("win-article");
        const clicksEl = document.getElementById("win-clicks");
        const timeEl = document.getElementById("win-time");

        // Replace underscores with spaces
        const targetName = data.end.replace(/_/g, ' ');

        articleEl.textContent = `Reached article: ${targetName}`;
        clicksEl.textContent = `Clicks: ${data.clicks}`;
        // Format time nicely
        let totalSeconds = Math.floor(data.elapsed); // remove decimals
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        const paddedSeconds = seconds.toString().padStart(2, '0');
        timeEl.textContent = `Time: ${minutes}:${paddedSeconds}`;

        // Show the modal
        document.getElementById("win-popup").classList.remove("hidden");

        // Home button
        document.getElementById("win-home").addEventListener("click", () => {
            window.location.href = "/";
        });
    }
}