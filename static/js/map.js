(() => {
    "use strict";
    const container = document.getElementById("places-map");
    if (!container) return;
    const failure = document.getElementById("map-failure");
    const tileFailure = document.getElementById("map-tile-failure");
    const categories = Object.freeze({
        attraction: "Attractions", dining: "Dining", shopping: "Shopping",
        accommodation: "Accommodation", nature: "Nature", heritage: "Heritage",
    });
    const fields = ["name", "detail_url", "category", "address", "latitude", "longitude"];
    let map;
    try {
        const data = document.getElementById("map-data");
        if (!data || !window.L) throw new Error("Map resources unavailable");
        const markers = JSON.parse(data.textContent);
        if (!Array.isArray(markers) || markers.length > 50) throw new Error("Invalid map data");
        // Presentation checks only. PlacesService remains the authoritative validator.
        // Validate every entry before creating a map or requesting any tiles.
        for (const marker of markers) {
            if (!marker || typeof marker !== "object" || Array.isArray(marker) ||
                Object.keys(marker).length !== fields.length ||
                !fields.every((field) => Object.hasOwn(marker, field)) ||
                ![marker.name, marker.address, marker.category, marker.detail_url]
                    .every((value) => typeof value === "string" && value.trim()) ||
                !Object.hasOwn(categories, marker.category) ||
                !Number.isFinite(marker.latitude) || Math.abs(marker.latitude) > 90 ||
                !Number.isFinite(marker.longitude) || Math.abs(marker.longitude) > 180) {
                throw new Error("Invalid map entry");
            }
            const url = new URL(marker.detail_url, window.location.href);
            if (url.origin !== window.location.origin ||
                !["http:", "https:"].includes(url.protocol) ||
                url.search || url.hash || url.username || url.password ||
                !/^\/(?:[A-Za-z0-9_-]+\/)*places\/[a-z0-9]+(?:-[a-z0-9]+)*$/.test(marker.detail_url)) {
                throw new Error("Invalid detail destination");
            }
        }
        if (!markers.length) return;
        const L = window.L;
        container.hidden = false;
        map = L.map(container, {
            scrollWheelZoom: false, zoomAnimation: false,
            fadeAnimation: false, markerZoomAnimation: false,
        });
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19, keepBuffer: 0, updateWhenIdle: true,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
        }).on("tileerror", () => {
            if (tileFailure) tileFailure.hidden = false;
        }).addTo(map);
        for (const marker of markers) {
            const popup = document.createElement("div");
            popup.className = "map-popup";
            for (const [tag, text] of [["strong", marker.name],
                ["p", categories[marker.category]], ["p", marker.address]]) {
                const element = document.createElement(tag);
                element.textContent = text;
                popup.appendChild(element);
            }
            const link = document.createElement("a");
            link.href = marker.detail_url;
            link.textContent = `View details for ${marker.name}`;
            popup.appendChild(link);
            L.marker([marker.latitude, marker.longitude], {
                title: marker.name, alt: marker.name, keyboard: true,
            }).addTo(map).bindPopup(popup, { maxWidth: 220, minWidth: 100 });
        }
        const positions = [...new Map(markers.map((marker) => [
            `${marker.latitude},${marker.longitude}`, [marker.latitude, marker.longitude],
        ])).values()];
        if (positions.length === 1) map.setView(positions[0], 14);
        else map.fitBounds(positions, { padding: [24, 24], maxZoom: 16 });
    } catch (_) {
        if (map) {
            try { map.remove(); } catch (_) { /* Keep the textual fallback available. */ }
        }
        container.hidden = true;
        if (failure) failure.hidden = false;
    }
})();
