/* ==========================================================================
   OTCloud - Application JavaScript
   Premium SaaS Dashboard
   ========================================================================== */

(function () {
  'use strict';

  /* ---------- DOM Ready ---------- */
  document.addEventListener('DOMContentLoaded', function () {
    initSidebar();
    initMessageAutoDismiss();
    initConfirmDialogs();
    initTimerDisplay();
    initTimeGreeting();
    initActiveNav();
    initSmoothScroll();
    initFormEnhancements();
  });

  /* ---------- Sidebar Toggle ---------- */
  function initSidebar() {
    var toggle = document.getElementById('sidebarToggle');
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');
    var closeBtn = document.getElementById('sidebarClose');

    if (!toggle || !sidebar) return;

    function openSidebar() {
      sidebar.classList.add('open');
      if (overlay) overlay.classList.add('active');
      document.body.classList.add('sidebar-open');
    }

    function closeSidebar() {
      sidebar.classList.remove('open');
      if (overlay) overlay.classList.remove('active');
      document.body.classList.remove('sidebar-open');
    }

    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      if (sidebar.classList.contains('open')) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });

    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        closeSidebar();
      });
    }

    if (overlay) {
      overlay.addEventListener('click', function () {
        closeSidebar();
      });
    }

    // Close sidebar on Escape key
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && sidebar.classList.contains('open')) {
        closeSidebar();
      }
    });

    // Close sidebar when clicking a nav link on mobile
    var navLinks = sidebar.querySelectorAll('.sidebar-link');
    navLinks.forEach(function (link) {
      link.addEventListener('click', function () {
        if (window.innerWidth < 1024) {
          closeSidebar();
        }
      });
    });

    // Handle resize: close sidebar if going to desktop
    var resizeTimer;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        if (window.innerWidth >= 1024) {
          closeSidebar();
        }
      }, 100);
    });
  }

  /* ---------- Time-based Greeting ---------- */
  function initTimeGreeting() {
    var el = document.getElementById('timeGreeting');
    if (!el) return;

    var hour = new Date().getHours();
    if (hour < 12) {
      el.textContent = 'morning';
    } else if (hour < 17) {
      el.textContent = 'afternoon';
    } else {
      el.textContent = 'evening';
    }
  }

  /* ---------- Active Nav Highlight ---------- */
  function initActiveNav() {
    var currentPath = window.location.pathname;
    var navLinks = document.querySelectorAll('.sidebar-link');

    navLinks.forEach(function (link) {
      // Skip if already marked active by server-side template
      if (link.classList.contains('active')) return;

      var href = link.getAttribute('href');
      if (!href || href === '#') return;

      // Exact match for dashboard, prefix match for others
      if (href === '/' && currentPath === '/') {
        link.classList.add('active');
      } else if (href !== '/' && currentPath.startsWith(href)) {
        link.classList.add('active');
      }
    });
  }

  /* ---------- Auto-Dismiss Messages ---------- */
  function initMessageAutoDismiss() {
    var alerts = document.querySelectorAll('.alert');

    alerts.forEach(function (alert) {
      // Close button
      var closeBtn = alert.querySelector('.alert-close');
      if (closeBtn) {
        closeBtn.addEventListener('click', function () {
          dismissAlert(alert);
        });
      }

      // Auto-dismiss after 5 seconds
      setTimeout(function () {
        dismissAlert(alert);
      }, 5000);
    });
  }

  function dismissAlert(alert) {
    if (!alert || alert.dataset.dismissed) return;
    alert.dataset.dismissed = 'true';
    alert.style.animation = 'fadeOut 0.3s ease forwards';
    setTimeout(function () {
      alert.remove();
    }, 300);
  }

  /* ---------- CSRF Token Helper ---------- */
  function getCSRFToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');

    var cookie = document.cookie.split(';').find(function (c) {
      return c.trim().startsWith('csrftoken=');
    });
    if (cookie) return cookie.split('=')[1];

    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input) return input.value;

    return '';
  }

  /**
   * POST request helper with CSRF token.
   * @param {string} url
   * @param {Object} data
   * @returns {Promise<Response>}
   */
  function postRequest(url, data) {
    var body;
    var headers = {
      'X-CSRFToken': getCSRFToken(),
      'X-Requested-With': 'XMLHttpRequest',
    };

    if (data instanceof FormData) {
      body = data;
    } else {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(data || {});
    }

    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: headers,
      body: body,
    });
  }

  // Expose helpers globally
  window.OTCloud = window.OTCloud || {};
  window.OTCloud.getCSRFToken = getCSRFToken;
  window.OTCloud.postRequest = postRequest;
  window.OTCloud.formatDuration = formatDuration;

  /* ---------- Confirm Dialogs ---------- */
  function initConfirmDialogs() {
    document.addEventListener('click', function (e) {
      var target = e.target.closest('[data-confirm]');
      if (!target) return;

      var message = target.getAttribute('data-confirm') || 'Are you sure?';
      if (!window.confirm(message)) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    });
  }

  /* ---------- Smooth Scroll ---------- */
  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
      anchor.addEventListener('click', function (e) {
        var targetId = this.getAttribute('href');
        if (targetId === '#') return;

        var target = document.querySelector(targetId);
        if (target) {
          e.preventDefault();
          target.scrollIntoView({
            behavior: 'smooth',
            block: 'start',
          });
        }
      });
    });
  }

  /* ---------- Form Enhancements ---------- */
  function initFormEnhancements() {
    // Auto-format phone number inputs
    document.querySelectorAll('input[type="tel"], input[name*="phone"], input[name*="mobile"]').forEach(function (input) {
      input.addEventListener('input', function () {
        var value = this.value.replace(/\D/g, '');
        if (value.length > 10) value = value.slice(0, 10);

        // Format as XXX-XXX-XXXX for display
        if (value.length >= 7) {
          this.value = value.slice(0, 3) + '-' + value.slice(3, 6) + '-' + value.slice(6);
        } else if (value.length >= 4) {
          this.value = value.slice(0, 3) + '-' + value.slice(3);
        } else {
          this.value = value;
        }
      });
    });

    // Character counters for textareas with maxlength
    document.querySelectorAll('textarea[maxlength]').forEach(function (textarea) {
      var max = parseInt(textarea.getAttribute('maxlength'), 10);
      if (!max) return;

      var counter = document.createElement('div');
      counter.className = 'char-counter';
      counter.textContent = '0 / ' + max;
      textarea.parentNode.insertBefore(counter, textarea.nextSibling);

      function updateCounter() {
        var len = textarea.value.length;
        counter.textContent = len + ' / ' + max;
        counter.classList.toggle('near-limit', len > max * 0.8 && len < max);
        counter.classList.toggle('at-limit', len >= max);
      }

      textarea.addEventListener('input', updateCounter);
      updateCounter();
    });

    // Add loading state to forms on submit
    document.querySelectorAll('form').forEach(function (form) {
      form.addEventListener('submit', function () {
        var submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
        if (submitBtn && !submitBtn.classList.contains('btn-loading')) {
          submitBtn.classList.add('btn-loading');
          submitBtn.disabled = true;

          // Re-enable after 8 seconds in case of issues
          setTimeout(function () {
            submitBtn.classList.remove('btn-loading');
            submitBtn.disabled = false;
          }, 8000);
        }
      });
    });
  }

  /* ---------- Live Timer for Attendance ---------- */
  var timerInterval = null;

  function initTimerDisplay() {
    var timerEl = document.getElementById('attendanceTimer');
    if (!timerEl) return;

    fetchTimer(timerEl);
    timerInterval = setInterval(function () {
      fetchTimer(timerEl);
    }, 1000);
  }

  function fetchTimer(timerEl) {
    fetch('/attendance/api/timer/', {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (res) {
        if (!res.ok) throw new Error('Timer fetch failed');
        return res.json();
      })
      .then(function (data) {
        if (data.is_checked_in && typeof data.elapsed_seconds === 'number') {
          timerEl.textContent = formatDuration(data.elapsed_seconds);
          timerEl.classList.add('timer-active');
        } else {
          timerEl.textContent = '00:00:00';
          timerEl.classList.remove('timer-active');
        }
      })
      .catch(function () {
        // Silently handle errors
      });
  }

  /**
   * Format seconds into HH:MM:SS string.
   * @param {number} totalSeconds
   * @returns {string}
   */
  function formatDuration(totalSeconds) {
    totalSeconds = Math.max(0, Math.floor(totalSeconds));
    var hours = Math.floor(totalSeconds / 3600);
    var minutes = Math.floor((totalSeconds % 3600) / 60);
    var seconds = totalSeconds % 60;

    return (
      String(hours).padStart(2, '0') +
      ':' +
      String(minutes).padStart(2, '0') +
      ':' +
      String(seconds).padStart(2, '0')
    );
  }
})();
