/* Presentation-only fallback for unavailable destination photos. No API calls,
   authentication, storage mutation or database assignment logic. */
(() => {
    'use strict';
    const source = document.currentScript?.dataset.destinationPlaceholder;
    if (!source) return;
    let placeholder;
    try {
        const url = new URL(source, window.location.href);
        if (url.origin !== window.location.origin || url.search || url.hash || url.username || url.password ||
            !url.pathname.endsWith('/static/img/destination-placeholder.svg')) return;
        placeholder = url.href;
    } catch (_) { return; }
    window.RosaGoImages = Object.freeze({placeholder});
    function fallback(image) {
        if (!image || image.tagName !== 'IMG' || !image.hasAttribute('data-destination-image')) return;
        const src = image.getAttribute('src');
        if (!src) return;
        try { if (new URL(src, window.location.href).href === placeholder) return; }
        catch (_) { /* Replace malformed presentation URLs with the local asset. */ }
        image.classList.add('destination-photo-placeholder');
        image.alt = image.dataset.placeholderAlt || 'Destination photo unavailable';
        image.src = placeholder;
    }
    // Image errors do not bubble. Capture also covers cards added after load.
    document.addEventListener('error', event => fallback(event.target), true);
    // Cached failures can occur before this deferred script has attached.
    for (const image of document.querySelectorAll('img[data-destination-image]')) {
        if (image.complete && image.naturalWidth === 0) fallback(image);
    }
})();
