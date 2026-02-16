/**
 * anthropic-custom-tracking.js
 * Analytics and tracking functionality for anthropic.com
 *
 * Contains:
 * - Universal sticky parameters (UTM tracking)
 * - Segment analytics event tracking
 * - Cross-domain link wrapping
 *
 * Dependencies: window.analytics (loaded by privacy banner)
 */

/* Universal Sticky Parameters // Tracks UTM params + gclid, fbclid, and any other custom parameters */

(function() {
  'use strict';

  // Configuration
  const CONFIG = {
    // Specify which parameters to track (leave empty to track ALL parameters)
    trackParams: [

      'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', // UTM parameters
      'gclid', 'dclid', 'gbraid', 'wbraid', // Google Ads parameters
      'fbclid', // Facebook parameters
      'msclkid', // Microsoft Ads parameters
      'li_fat_id', // LinkedIn parameters
      // Add your custom parameters here
      // 'custom_param1', 'custom_param2'
    ],
    // OR set to true to track ALL URL parameters
    trackAllParams: true,

    // Parameters to EXCLUDE from tracking (only used if trackAllParams is true)
    excludeParams: [
      'page', 'tab', 'section', 'sort', 'filter', 'search', 'id'
    ],

    storageKey: 'tracking_params',
    domainExcludePatterns: [
      /^mailto:/,
      /^tel:/,
      /^javascript:/,
      /^#/,
      /^sms:/,
      /\.pdf$/,
      /\.jpg$/,
      /\.png$/,
      /\.gif$/
    ],
    maxObserverTime: 5000, // 5 seconds
    observerDebounceMs: 200,
    sessionLength: 30, // How long to persist parameters (in minutes)
    debug: false // Set to true to enable console logging
  };

  // Debug logger
  const log = function(...args) {
    if (CONFIG.debug) {
      console.log('[Param Tracker]', ...args);
    }
  };

  // Utility Functions
  const utils = {
    // Debounce function to limit executions
    debounce: function(func, wait) {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    },

    // Get all tracking parameters from URL
    getTrackingParams: function() {
      const urlParams = new URLSearchParams(window.location.search);
      const params = {};

      if (CONFIG.trackAllParams) {
        // Track all parameters except excluded ones
        for (const [key, value] of urlParams.entries()) {
          if (!CONFIG.excludeParams.includes(key.toLowerCase())) {
            params[key] = value;
          }
        }
      } else {
        // Track only specified parameters
        CONFIG.trackParams.forEach(param => {
          const value = urlParams.get(param);
          if (value) {
            params[param] = value;
          }
        });
      }

      log('Extracted params:', params);
      return params;
    },

    // Store parameters with expiration
    storeTrackingParams: function(params) {
      if (Object.keys(params).length > 0) {
        try {
          const data = {
            params: params,
            expiry: Date.now() + (CONFIG.sessionLength * 60 * 1000)
          };
          sessionStorage.setItem(CONFIG.storageKey, JSON.stringify(data));
          log('Stored params:', data);
        } catch (e) {
          log('Storage failed:', e);
        }
      }
    },

    // Retrieve stored parameters
    getStoredTrackingParams: function() {
      try {
        const stored = sessionStorage.getItem(CONFIG.storageKey);
        if (!stored) return {};

        const data = JSON.parse(stored);

        // Check if expired
        if (Date.now() > data.expiry) {
          sessionStorage.removeItem(CONFIG.storageKey);
          log('Parameters expired');
          return {};
        }

        log('Retrieved params:', data.params);
        return data.params || {};
      } catch (e) {
        log('Retrieval failed:', e);
        return {};
      }
    },

    // Append parameters to URL
    appendParameters: function(url, params) {
      if (!url || typeof url !== 'string') return url;

      try {
        // Handle relative and absolute URLs
        const urlObj = new URL(url, window.location.origin);

        // Skip external domains (unless it's a subdomain)
        const currentHost = window.location.hostname;
        const urlHost = urlObj.hostname;
        if (urlHost !== currentHost && !urlHost.endsWith('.' + currentHost.split('.').slice(-2).join('.'))) {
          return url;
        }

        // Add parameters
        Object.keys(params).forEach(key => {
          if (!urlObj.searchParams.has(key)) {
            urlObj.searchParams.set(key, params[key]);
          }
        });

        return urlObj.toString();
      } catch (e) {
        // Fallback for malformed URLs
        if (url.indexOf('?') === -1) {
          const paramString = Object.keys(params).map(key => `${key}=${encodeURIComponent(params[key])}`).join('&');
          return `${url}?${paramString}`;
        }
        return url;
      }
    },

    // Check if URL should be excluded
    shouldExcludeURL: function(url) {
      return CONFIG.domainExcludePatterns.some(pattern => pattern.test(url));
    }
  };

  // Link update function
  function updateLinks() {
    const storedParams = utils.getStoredTrackingParams();

    if (Object.keys(storedParams).length === 0) return;

    // Use querySelectorAll for better performance
    const links = document.querySelectorAll('a[href]');

    links.forEach(link => {
      const href = link.getAttribute('href');

      // Skip if URL should be excluded
      if (!href || utils.shouldExcludeURL(href)) return;

      // Check if it's an internal link
      const newHref = utils.appendParameters(href, storedParams);
      if (newHref !== href) {
        link.setAttribute('href', newHref);
        log('Updated link:', href, '→', newHref);
      }
    });
  }

  // Optimized mutation observer
  let observer;
  function setupObserver() {
    // Debounced update function
    const debouncedUpdate = utils.debounce(updateLinks, CONFIG.observerDebounceMs);

    observer = new MutationObserver((mutations) => {
      // Check if any mutation contains new links
      const hasNewLinks = mutations.some(mutation => {
        return Array.from(mutation.addedNodes).some(node =>
                                                    node.nodeType === 1 && (node.tagName === 'A' || node.querySelector('a'))
                                                    );
      });

      if (hasNewLinks) {
        debouncedUpdate();
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });

    // Disconnect observer after timeout to prevent memory leaks
    setTimeout(() => {
      if (observer) {
        observer.disconnect();
        observer = null;
        log('Observer disconnected');
      }
    }, CONFIG.maxObserverTime);
  }

  // Initialize function
  function init() {
    log('Initializing...');

    // Get tracking parameters from current URL
    const currentParams = utils.getTrackingParams();

    // Store new parameters if present
    if (Object.keys(currentParams).length > 0) {
      utils.storeTrackingParams(currentParams);
    }

    // Initial link update
    updateLinks();

    // Setup mutation observer
    setupObserver();
  }

  // Event listeners
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Handle browser navigation
  window.addEventListener('popstate', init);

  // Clean up on page unload (optional)
  window.addEventListener('beforeunload', () => {
    if (observer) {
      observer.disconnect();
    }
  });

  // Expose API for external use (optional)
  window.paramTracker = {
    getStoredParams: utils.getStoredTrackingParams,
    refreshLinks: updateLinks,
    addCustomParams: function(customParams) {
      const currentParams = utils.getStoredTrackingParams();
      const mergedParams = Object.assign({}, currentParams, customParams);
      utils.storeTrackingParams(mergedParams);
      updateLinks();
    },
    clearParams: function() {
      sessionStorage.removeItem(CONFIG.storageKey);
      log('Parameters cleared');
    }
  };
})();


/* Segment tracking */

document.addEventListener('DOMContentLoaded', function() {
  function initSegmentTracking() {
    // Wait for Segment to be ready
    window.analytics.ready(function() {

      // Send custom Page Viewed event
    window.analytics.track('anthropicdotcom.page.viewed', {
      page_title: document.title,
      page_url: window.location.href,
      page_path: window.location.pathname,
      referrer: document.referrer || 'direct'
    });

    // Track clicks on elements with data-cta attribute
    document.addEventListener('click', function(event) {
      const element = event.target;
      const ctaElement = element.closest('[data-cta]');
      if (ctaElement) {
        const ctaData = {
          cta: ctaElement.getAttribute('data-cta'),
          cta_copy: ctaElement.getAttribute('data-cta-copy'),
          cta_position: ctaElement.getAttribute('data-cta-position')
        };
        Object.keys(ctaData).forEach(key => {
          if (ctaData[key] === null || ctaData[key] === undefined) {
            delete ctaData[key];
          }
        });
        window.analytics.track('anthropicdotcom.cta.clicked', ctaData);
      }
    });

    // Track Iterable newsletter form submissions
    document.querySelectorAll('[data-form="iterable"]').forEach((form, index) => {
      // Ensure form wrapper exists
      const formWrapper = form.closest('.w-form');
      if (!formWrapper) return;

      // Flag to prevent duplicate tracking
      let isTracking = false;

      form.addEventListener('submit', function(e) {
        if (isTracking) return;
        isTracking = true;

        // Capture form data at submission time
        const emailField = form.querySelector('input[type="email"]');
        const emailValue = emailField ? emailField.value.toLowerCase().trim() : '';

        // Build consistent event properties
        const baseProperties = {
          email: emailValue,
          form_name: form.getAttribute('data-name') || 'newsletter',
          form_id: form.getAttribute('id') || `newsletter-form-${index}`,
          page_path: window.location.pathname,
          page_url: window.location.href,
          page_title: document.title,
          referrer: document.referrer || 'direct',
          timestamp: new Date().toISOString()
        };

        // Monitor for Webflow's response
        let attempts = 0;
        const maxAttempts = 30; // 15 seconds maximum

        const checkFormState = setInterval(() => {
          attempts++;

          // Check for success state
          const successBlock = formWrapper.querySelector('.w-form-done');
          const errorBlock = formWrapper.querySelector('.w-form-fail');
          const successVisible = successBlock && window.getComputedStyle(successBlock).display === 'block';
          const errorVisible = errorBlock && window.getComputedStyle(errorBlock).display === 'block';

          if (successVisible) {
            // Track successful subscription
            window.analytics.track('anthropicdotcom.newsletter.subscribed', baseProperties);
            clearInterval(checkFormState);
            isTracking = false;

            // Optional: Clear form after success
            form.reset();

          } else if (errorVisible) {
            // Track error
            const errorText = errorBlock.textContent?.trim() || 'Unknown error';
            window.analytics.track('anthropicdotcom.newsletter.error', {
              ...baseProperties,
              error_message: errorText,
              error_type: errorText.toLowerCase().includes('already') ? 'duplicate_email' : 'submission_error'
            });
            clearInterval(checkFormState);
            isTracking = false;

          } else if (attempts >= maxAttempts) {
            // Timeout - track as error
            window.analytics.track('anthropicdotcom.newsletter.error', {
              ...baseProperties,
              error_message: 'Form submission timeout',
              error_type: 'timeout'
            });
            clearInterval(checkFormState);
            isTracking = false;
          }
        }, 500);
      });
    });

    // Track app download button clicks
      // Usage: Add data-app-download="platform" to download buttons (e.g., data-app-download="ios")
      document.addEventListener("click", function (event) {
        const downloadButton = event.target.closest("[data-app-download]");

        if (downloadButton) {
          // Get the platform from the button's data attribute value
          const buttonPlatform = downloadButton.getAttribute("data-app-download");

          // Detect user's platform
          const userAgent = navigator.userAgent.toLowerCase();
          let userPlatform = "other";


          if (userAgent.includes("iphone") || userAgent.includes("ipad") ||  (userAgent.includes("mac") && "ontouchend" in document)) {
            userPlatform = "ios";
          } else if (userAgent.includes("macintosh")) {
            userPlatform = "mac";
          } else if (userAgent.includes("android")) {
            userPlatform = "android";
          } else if (userAgent.includes("windows") || userAgent.includes("win32") || userAgent.includes("win64")) {
            if (userAgent.includes("arm") || userAgent.includes("aarch64") || userAgent.includes("arm64")) {
              userPlatform = "win-arm64";
            } else {
              userPlatform = "win-x64";
            }
          }

          // Track the event
          window.analytics.track("apps.download_button_clicked", {
            platform: buttonPlatform,
            userPlatform: userPlatform,
            source: "download_page",
          });
        }
      });
    });
  }

  // Wait for analytics to be available (may not be loaded yet due to async privacy banner)
  // This handles the race condition where custom-tracking runs before privacy-banner
  // has finished loading Segment analytics
  if (window.analytics && typeof window.analytics.ready === 'function') {
    initSegmentTracking();
  } else {
    // Retry until analytics is available or timeout after 10 seconds
    let attempts = 0;
    const maxAttempts = 20;
    const checkInterval = setInterval(function() {
      attempts++;
      if (window.analytics && typeof window.analytics.ready === 'function') {
        clearInterval(checkInterval);
        initSegmentTracking();
      } else if (attempts >= maxAttempts) {
        // Analytics never loaded (user likely declined consent)
        clearInterval(checkInterval);
      }
    }, 500);
  }
});



/* Cross-Domain Link Script */

/* It automatically wraps claude.ai links with anonymous IDs for tracking. This is a no-op if Segment analytics is not initialized */

(function() {
  let observer;
  const sourceAttribution = 'website.v1';

  function wrapLinks(container = document) {
    if (!window.analytics?.user) return;

    let anonymousId = window.analytics.user().anonymousId();
    if (!anonymousId) return;

    // Check if the anonymous ID already has our prefix
    if (!anonymousId.startsWith(sourceAttribution + '.')) {
      const fullId = `${sourceAttribution}.${anonymousId}`;
      try {
        window.analytics.user().anonymousId(fullId);
        anonymousId = fullId;
      } catch (error) {
        // Silent fail, use original ID
      }
    }

    container.querySelectorAll('a[href*="claude.ai"]:not([href*="/redirect/"])').forEach(link => {
      try {
        const url = new URL(link.href);
        if (url.hostname.endsWith('claude.ai')) {
          const originalPath = url.pathname === '/' ? '' : url.pathname;
          url.pathname = `/redirect/${anonymousId}${originalPath}`;
          link.href = url.toString();
        }
      } catch (error) {
        // Silent fail, leave link unchanged
      }
    });
  }

  function startObserver() {
    if (!window.analytics?.user) return;

    if (observer) observer.disconnect();

    observer = new MutationObserver(mutations => {
      mutations.forEach(mutation => {
        mutation.addedNodes.forEach(node => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            if (node.tagName === 'A' && node.href && node.href.includes('claude.ai')) {
              wrapLinks(node.parentElement);
            } else if (node.querySelector) {
              const claudeLinks = node.querySelectorAll('a[href*="claude.ai"]');
              if (claudeLinks.length > 0) {
                wrapLinks(node);
              }
            }
          }
        });
      });
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  function initialize() {
    wrapLinks();
    startObserver();
    // Send page call here instead of init in case anon id was updated
    if (window.analytics?.page) {
      window.analytics.page();
    }
  }

  function waitForAnalytics(attempt = 1) {
    if (window.analytics && window.analytics.user) {
      initialize();
    } else if (window.analytics && window.analytics.ready && attempt === 1) {
      const readyTimeout = setTimeout(() => {
        waitForAnalytics(2);
      }, 3000);

      window.analytics.ready(() => {
        clearTimeout(readyTimeout);
        initialize();
      });
    } else {
      if (attempt > 20) return;
      setTimeout(() => waitForAnalytics(attempt + 1), 500);
    }
  }

  if (window.analytics) {
    waitForAnalytics();
  } else {
    window.addEventListener('load', () => {
      setTimeout(waitForAnalytics, 1000);
    });
  }

  window.addEventListener('beforeunload', () => {
    if (observer) observer.disconnect();
  });
})();
