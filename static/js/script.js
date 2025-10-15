document.addEventListener("DOMContentLoaded", () => {
  // --- DOM ELEMENT REFERENCES ---
  const guidelinesContainer = document.getElementById(
    "common-guidelines-container"
  );
  const commonContainer = document.getElementById(
    "common-notifications-container"
  );
  const deptContainer = document.getElementById(
    "department-notifications-container"
  );
  const archiveContainer = document.getElementById(
    "archive-notifications-container"
  );
  const departmentSelect = document.getElementById("department-select");
  const yearSelect = document.getElementById("year-select");

  const modalOverlay = document.createElement("div");
  modalOverlay.classList.add("modal-overlay");
  modalOverlay.innerHTML = `
    <div class="modal-content">
      <button class="close-button">&times;</button>
      <h3 id="modal-title">Notification Details</h3>
      <div id="modal-body"></div>
    </div>`;
  document.body.appendChild(modalOverlay);
  const modalBody = modalOverlay.querySelector("#modal-body");
  const modalClose = modalOverlay.querySelector(".close-button");

  // --- WORD WHEEL SETUP ---
  function setupWordWheel() {
    const wordWheel = document.querySelector(".word-wheel");
    const textArray = [
      "deadlines.",
      "notifications.",
      "guidelines.",
      "results.",
    ];
    if (wordWheel && textArray.length > 0) {
      const wordsToDisplay = [...textArray, textArray[0]];
      wordWheel.innerHTML = wordsToDisplay
        .map((word) => `<span class="word-wheel-item">${word}</span>`)
        .join("");
    }
  }

  // --- FETCH & RENDER LOGIC ---
  function handleSelectionChange() {
    const department = departmentSelect.value;
    const year = yearSelect.value;
    if (department && year) {
      fetchNotifications(department, year);
    } else {
      fetchNotifications(); // Fetch common/guidelines/archive even if nothing is selected
    }
  }

  async function fetchNotifications(department = null, year = null) {
    let apiUrl = "/api/notifications";
    if (department && year) {
      apiUrl += `?department=${department}&year=${year}`;
      deptContainer.innerHTML = `<div class="loading-overlay"><div class="spinner"></div></div>`;
    }

    try {
      const response = await fetch(apiUrl);
      if (!response.ok) throw new Error("Failed to fetch notifications");
      const data = await response.json();

      // Always render these
      renderNotifications(
        guidelinesContainer,
        data.guidelines,
        "guideline",
        true
      );
      renderNotifications(commonContainer, data.common, "common", true);
      renderNotifications(archiveContainer, data.archive, "archive", false);

      if (department && year) {
        renderNotifications(
          deptContainer,
          data.departmental,
          "departmental",
          false
        );
        const urgentPopup = data.departmental.find((n) => n.is_popup);
        if (urgentPopup) showPopup(urgentPopup);
      } else {
        deptContainer.innerHTML = `<div class="info-box"><i class="fas fa-arrow-up"></i> Select a department and year to see specific updates.</div>`;
      }
    } catch (error) {
      console.error("Error fetching notifications:", error);
      deptContainer.innerHTML = `<div class="info-box error"><i class="fas fa-exclamation-circle"></i> Could not load notifications.</div>`;
    }
  }

  function renderNotifications(container, notifications, type, isSide) {
    container.innerHTML = "";
    if (!notifications || notifications.length === 0) {
      if (container !== archiveContainer) {
        // Don't show "no notifications" for archive if it's empty
        container.innerHTML = `<div class="info-box compact"><i class="fas fa-info-circle"></i> No active ${type}s.</div>`;
      }
      return;
    }

    notifications.forEach((notif) => {
      const card = document.createElement("div");
      card.className = isSide
        ? `notification-card-side ${notif.type || "info"}`
        : `notification-card ${notif.type || "info"}`;
      let attachmentHTML = "";
      if (notif.attachment_url) {
        attachmentHTML = `<a href="${notif.attachment_url}" target="_blank" rel="noopener noreferrer" class="attachment-link">🔗 View Attachment</a>`;
      }
      const postedDate = new Date(notif.start_datetime).toLocaleDateString(
        "en-IN",
        { day: "numeric", month: "short", year: "numeric" }
      );

      if (isSide) {
        card.innerHTML = `<h4>${notif.title}</h4><div class="meta">${postedDate}</div>`;
        card.addEventListener("click", () => showPopup(notif));
      } else {
        card.innerHTML = `<h4>${notif.title}</h4><div class="meta"><span><strong>Posted:</strong> ${postedDate}</span></div><p>${notif.body}</p>${attachmentHTML}`;
      }
      container.appendChild(card);
    });

    if (!isSide) {
      observeCards();
    }
  }

  // --- Modal & Observer Functions (Unchanged) ---
  function showPopup(notif) {
    modalBody.innerHTML = `<p>${
      notif.body || "No further details available."
    }</p>`;
    if (notif.attachment_url) {
      modalBody.innerHTML += `<br><a href="${notif.attachment_url}" target="_blank" rel="noopener noreferrer" class="attachment-link">🔗 View Attachment</a>`;
    }
    modalOverlay.querySelector("#modal-title").textContent = notif.title;
    modalOverlay.classList.add("active");
  }
  function hidePopup() {
    modalOverlay.classList.remove("active");
  }
  modalClose.addEventListener("click", hidePopup);
  modalOverlay.addEventListener("click", (e) => {
    if (e.target === modalOverlay) hidePopup();
  });
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1 }
  );
  function observeCards() {
    document
      .querySelectorAll(".notification-card:not(.visible)")
      .forEach((card) => observer.observe(card));
  }

  // --- INITIALIZATION ---
  departmentSelect.addEventListener("change", handleSelectionChange);
  yearSelect.addEventListener("change", handleSelectionChange);
  setupWordWheel();
  handleSelectionChange(); // Initial fetch
  document.getElementById("year").textContent = new Date().getFullYear();
});
