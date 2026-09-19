/* 极简内联图标集（stroke 风格），原型专用 */
(function () {
  const P = {
    inbox: '<path d="M3 12h5l2 3h4l2-3h5"/><path d="M5.5 5h13l2.5 7v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6z"/>',
    news: '<path d="M4 5h16M4 11h16M4 17h10"/>',
    cluster: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.2 7.6 10.8 16M15.8 7.6 13.2 16M8.5 6h7"/>',
    pen: '<path d="M4 20h4l10-10a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5 17.5 10.5"/>',
    shield: '<path d="M12 3l7 3v6c0 4.2-2.9 7.6-7 9-4.1-1.4-7-4.8-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    wand: '<path d="M5 19 16 8"/><path d="M14 4l1.5 3 3 1.5-3 1.5L14 13l-1.5-3L9 8.5 12 7z"/><path d="M19 15l.8 1.6 1.7.8-1.7.8-.8 1.6-.8-1.6-1.7-.8 1.7-.8z"/>',
    spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
    check: '<path d="M5 12.5 9.5 17 19 7"/>',
    checkCircle: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5 11 15.5 16.5 9"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    xCircle: '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    alert: '<path d="M12 4 3 20h18z"/><path d="M12 10v4M12 17.5v.5"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
    star: '<path d="m12 4 2.5 5.2 5.5.8-4 3.9 1 5.6-5-2.9-5 2.9 1-5.6-4-3.9 5.5-.8z"/>',
    bookmark: '<path d="M6 4h12v16l-6-4-6 4z"/>',
    eye: '<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="2.6"/>',
    eyeOff: '<path d="M4 4l16 16"/><path d="M9.5 5.5A9.8 9.8 0 0 1 12 5.4c6.4 0 10 5.6 10 5.6a17 17 0 0 1-3.4 3.9"/><path d="M6.4 7.6A17 17 0 0 0 2 11c0 0 3.6 5.6 10 5.6 1 0 1.9-.1 2.7-.4"/><path d="M9.6 9.9a2.6 2.6 0 0 0 3.6 3.7"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
    filter: '<path d="M3 5h18l-7 8v6l-4 2v-8z"/>',
    download: '<path d="M12 4v11"/><path d="m7.5 10.5 4.5 4.5 4.5-4.5"/><path d="M4 19h16"/>',
    chevronDown: '<path d="m6 9 6 6 6-6"/>',
    chevronRight: '<path d="m9 6 6 6-6 6"/>',
    chevronUp: '<path d="m6 15 6-6 6 6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    trash: '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.5l3.5 2"/>',
    link: '<path d="M10 13a4 4 0 0 0 5.7 0l2.6-2.6a4 4 0 0 0-5.7-5.7L11.5 6"/><path d="M14 11a4 4 0 0 0-5.7 0L5.7 13.6a4 4 0 0 0 5.7 5.7L12.5 18"/>',
    db: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    user: '<circle cx="12" cy="8" r="3.6"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    tag: '<path d="M3 12V4h8l9 9-8 8z"/><circle cx="7.5" cy="7.5" r="1.2"/>',
    flag: '<path d="M5 21V4h13l-2.5 4.5L18 13H5"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18"/>',
    bulb: '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5.9 1.2.9 2h5.2c0-.8.3-1.5.9-2A6 6 0 0 0 12 3z"/>',
    quote: '<path d="M8 7c-2.5 0-4 1.8-4 4.2S5.5 15 8 15v2l3-3.5c0-3.5-1.2-6.5-3-6.5z"/><path d="M18 7c-2.5 0-4 1.8-4 4.2S15.5 15 18 15v2l3-3.5c0-3.5-1.2-6.5-3-6.5z"/>',
    lock: '<rect x="4.5" y="10" width="15" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    bolt: '<path d="M13 3 5 14h5l-1 7 8-11h-5z"/>',
  };

  window.Icon = function (name, cls) {
    const d = P[name] || P.file;
    return '<svg class="ico ' + (cls || '') + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
      + 'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + '</svg>';
  };
})();
