// Google Analytics 4 on the public swelter pages (ADR 0055).
//
// GA4_ID below is the one place the measurement ID goes. It is public: every page that loads GA
// sends it to the browser. Set it to "" and this file does nothing at all: no Google request, no
// `dataLayer`, and no `window.swelterAnalytics`, so the footer opt-out control stays hidden.
//
// With an ID set, it publishes `window.swelterAnalytics` (the footer control in app.js and
// planner.js reads and changes the opt-out through it) and then returns before creating
// `dataLayer` or asking Google for anything unless every one of these holds:
//
// - the page is served over HTTPS from chelseakr.github.io under /swelter/ (the dashboard, the
//   /sensors/ route and the planner), so local previews, `swelter serve`, the Playwright, pa11y and
//   Lighthouse servers on 127.0.0.1, CI and any collective's own deployment load nothing;
// - the browser does not send Global Privacy Control (`navigator.globalPrivacyControl === true`);
// - Do Not Track is off (`navigator.doNotTrack`, `window.doNotTrack` or `navigator.msDoNotTrack`
//   is not "1" or "yes"); and
// - the visitor has not opted out in the footer (localStorage OPT_OUT_KEY is "1").
//
// Then it sets Consent Mode v2 defaults (the three advertising signals denied everywhere;
// analytics storage denied in the EEA, the UK and Switzerland, so Google receives cookieless
// pings from there, and granted elsewhere) and configures GA with Google signals and ad
// personalization off. `page_location` is the page's origin and path only, so the `#p=…&l=…`
// view state (which names a map cell) and any query string never reach Google, and
// `page_referrer` is the linking site's origin only. Locations, searches, thresholds and every
// other saved setting are never read by this file.
(function () {
  "use strict";

  // The one place the measurement ID goes. "" = no Google Analytics anywhere.
  // G-CMSGSNGC9P is the web stream of GA4 property 554836705 (provisioned 2026-09-17 with
  // 14-month retention and Google signals disabled).
  var GA4_ID = "G-CMSGSNGC9P";
  var PRODUCTION_HOST = "chelseakr.github.io";
  var PRODUCTION_PATH = "/swelter/";
  // Renaming this key would silently opt every opted-out visitor back in. It is deliberately not
  // part of "swelter.prefs", so "Clear saved settings" never undoes an opt-out.
  var OPT_OUT_KEY = "swelter.analytics-opt-out";
  var LOADER = "https://www.googletagmanager.com/gtag/js?id=";
  // analytics_storage stays denied for these ISO 3166-1 regions: the 27 EU member states,
  // Iceland, Liechtenstein and Norway (the EEA), the United Kingdom and Switzerland.
  var CONSENT_REQUIRED = [
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
    "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    "IS", "LI", "NO",
    "GB",
    "CH",
  ];

  if (!/^G-[A-Z0-9]{4,20}$/.test(GA4_ID)) return;

  var w = window;
  var n = w.navigator || {};
  var d = document;

  var store = null;
  try {
    store = w.localStorage;
    store.getItem(OPT_OUT_KEY);
  } catch (e) {
    store = null;
  }
  function optedOut() {
    try {
      return !!store && store.getItem(OPT_OUT_KEY) === "1";
    } catch (e) {
      return false;
    }
  }
  var dnt = n.doNotTrack || w.doNotTrack || n.msDoNotTrack;
  var signal = n.globalPrivacyControl === true || dnt === "1" || dnt === "yes";

  w.swelterAnalytics = Object.freeze({
    blockedBySignal: signal,
    storageAvailable: function () {
      return !!store;
    },
    isOptedOut: optedOut,
    // Returns false when storage refuses the write; the caller says so instead of pretending.
    setOptedOut: function (value) {
      try {
        if (value) store.setItem(OPT_OUT_KEY, "1");
        else store.removeItem(OPT_OUT_KEY);
      } catch (e) {
        store = null;
        return false;
      }
      w["ga-disable-" + GA4_ID] = !!value;
      return true;
    },
  });
  // The dashboard loads this file after app.js, so the footer control may be wired before
  // the API above exists. app.js listens for this once and wires the control then.
  try {
    d.dispatchEvent(new Event("swelter:analytics"));
  } catch (e) {
    // No DOM events (a test harness, a very old browser): app.js's direct check still runs.
  }

  var loc = w.location;
  if (loc.protocol !== "https:" || loc.hostname !== PRODUCTION_HOST) return;
  if (loc.pathname.indexOf(PRODUCTION_PATH) !== 0) return;
  if (signal) return;
  if (optedOut()) return;

  function referrerOrigin() {
    var ref = d.referrer;
    if (!ref) return "";
    try {
      return new URL(ref).origin + "/";
    } catch (e) {
      return "";
    }
  }

  w.dataLayer = w.dataLayer || [];
  // gtag reads the arguments object itself, not an array made from it.
  function gtag() {
    w.dataLayer.push(arguments);
  }
  gtag("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "denied",
    region: CONSENT_REQUIRED,
  });
  gtag("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "granted",
  });
  gtag("js", new Date());
  gtag("config", GA4_ID, {
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
    page_location: loc.origin + loc.pathname,
    page_referrer: referrerOrigin(),
  });

  var script = d.createElement("script");
  script.async = true;
  script.src = LOADER + encodeURIComponent(GA4_ID);
  (d.head || d.documentElement).appendChild(script);
})();
