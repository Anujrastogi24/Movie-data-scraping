if (window.Swiper) {
  new Swiper(".popular-content", {
    slidesPerView: 1,
    spaceBetween: 10,
    autoplay: {
      delay: 5500,
      disableOnInteraction: false,
    },
    pagination: {
      el: ".swiper-pagination",
      clickable: true,
    },
    navigation: {
      nextEl: ".swiper-button-next",
      prevEl: ".swiper-button-prev",
    },
    breakpoints: {
      280: { slidesPerView: 1, spaceBetween: 10 },
      320: { slidesPerView: 2, spaceBetween: 10 },
      510: { slidesPerView: 3, spaceBetween: 15 },
      900: { slidesPerView: 4, spaceBetween: 20 },
    },
  });
}

const videoContainer = document.querySelector(".video-container");
const video = document.querySelector("#myvideo");
const source = document.querySelector("#src1");
const embedPlayer = document.querySelector("#embed-player");
const openVideoButton = document.querySelector(".open-video");
const closeVideoButton = document.querySelector(".close-video");
const playContainer = document.querySelector(".playable-thumbnail");
const inlineEmbedPlayer = document.querySelector("#inline-embed-player");
const inlineVideoPlayer = document.querySelector("#inline-video-player");
const inlineVideoSource = document.querySelector("#inline-video-source");

function openPlayer(url, playerType) {
  if (!videoContainer) return;
  setPlaySrc(url, playerType);
  videoContainer.classList.add("show-video");
  if (video && playerType !== "iframe") video.play().catch(() => {});
}

function setPlaySrc(url, playerType) {
  if (!url) return;

  if (playerType === "iframe") {
    if (video) {
      video.pause();
      video.removeAttribute("src");
      if (source) source.removeAttribute("src");
      video.load();
      video.classList.add("is-hidden");
    }
    if (embedPlayer) {
      embedPlayer.src = url;
      embedPlayer.classList.remove("is-hidden");
    }
    return;
  }

  if (!video) return;
  if (embedPlayer) {
    embedPlayer.removeAttribute("src");
    embedPlayer.classList.add("is-hidden");
  }
  video.classList.remove("is-hidden");
  if (source) source.src = url;
  video.src = url;
  video.load();
}

if (playContainer) {
  playContainer.addEventListener("click", (event) => {
    if (event.target.closest("a, button, .video-container")) return;
    openPlayer(playContainer.dataset.src, playContainer.dataset.player);
  });

  playContainer.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    openPlayer(playContainer.dataset.src, playContainer.dataset.player);
  });
}

if (openVideoButton) {
  openVideoButton.addEventListener("click", () => {
    openPlayer(openVideoButton.dataset.src, openVideoButton.dataset.player);
  });
}

if (closeVideoButton && videoContainer && video) {
  closeVideoButton.addEventListener("click", () => {
    video.pause();
    if (embedPlayer) embedPlayer.removeAttribute("src");
    videoContainer.classList.remove("show-video");
  });
}

document.querySelectorAll(".server-btn").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.classList.contains("inline-server-btn")) return;
    openPlayer(button.dataset.src, button.dataset.player);
  });
});

function setInlinePlayer(url, playerType) {
  if (!url) return;

  if (playerType === "iframe") {
    if (inlineVideoPlayer) {
      inlineVideoPlayer.pause();
      inlineVideoPlayer.removeAttribute("src");
      if (inlineVideoSource) inlineVideoSource.removeAttribute("src");
      inlineVideoPlayer.load();
      inlineVideoPlayer.classList.add("is-hidden");
    }
    if (inlineEmbedPlayer) {
      inlineEmbedPlayer.src = url;
      inlineEmbedPlayer.classList.remove("is-hidden");
    }
    return;
  }

  if (inlineEmbedPlayer) {
    inlineEmbedPlayer.removeAttribute("src");
    inlineEmbedPlayer.classList.add("is-hidden");
  }
  if (inlineVideoPlayer) {
    inlineVideoPlayer.classList.remove("is-hidden");
    if (inlineVideoSource) inlineVideoSource.src = url;
    inlineVideoPlayer.src = url;
    inlineVideoPlayer.load();
  }
}

document.querySelectorAll(".inline-server-btn").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".inline-server-btn").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    setInlinePlayer(button.dataset.src, button.dataset.player);
  });
});

/* ---- Mobile navigation (hamburger drawer + tap-to-expand menus) ---- */
(function () {
  const nav = document.querySelector(".nav");
  const toggle = document.getElementById("nav-toggle");

  if (nav && toggle) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("nav-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // Genre / Year dropdowns: tap to expand inside the drawer.
  // On desktop (>1024px) the menus open on hover, so we leave them alone.
  const isMobileNav = () => window.matchMedia("(max-width: 1024px)").matches;

  document.querySelectorAll(".site-menu .menu-dropdown > button").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      if (!isMobileNav()) return;
      event.preventDefault();
      const parent = btn.parentElement;
      const willOpen = !parent.classList.contains("open");
      document.querySelectorAll(".site-menu .menu-dropdown.open").forEach((open) => {
        if (open !== parent) open.classList.remove("open");
      });
      parent.classList.toggle("open", willOpen);
    });
  });
})();
