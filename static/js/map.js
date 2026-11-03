(() => {
    "use strict";
    const container = document.getElementById("places-map");
    if (!container) return;
    const failure = document.getElementById("map-failure");
    const tileFailure = document.getElementById("map-tile-failure");
    const categories = Object.freeze({
        attraction: "Attractions", dining: "Dining", shopping: "Shopping",
        accommodation: "Accommodation", nature: "Nature", heritage: "Heritage", industrial: "Industrial Tourism",
    });
    const fields = ["name", "detail_url", "category", "address", "latitude", "longitude"];
    let map;
    try {
        const data = document.getElementById("map-data");
        if (!data || !window.L) throw new Error("Map resources unavailable");
        const markers = JSON.parse(data.textContent);
        if (!Array.isArray(markers)) throw new Error("Invalid map data");
        // Presentation checks only. PlacesService remains the authoritative validator.
        // Validate every entry before creating a map or requesting any tiles.
        for (const marker of markers) {
            if (!marker || typeof marker !== "object" || Array.isArray(marker) ||
                Object.keys(marker).some(field => ![...fields, 'tourism_type'].includes(field)) ||
                (marker.tourism_type != null && !['Local','Common'].includes(marker.tourism_type)) ||
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
        const form = document.getElementById("route-form");
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
                ["p", [categories[marker.category],marker.tourism_type].filter(Boolean).join(" \u00b7 ")], ["p", marker.address]]) {
                const element = document.createElement(tag);
                element.textContent = text;
                popup.appendChild(element);
            }
            const link = document.createElement("a");
            link.href = marker.detail_url;
            link.textContent = "View Details";
            link.className = "mini-button";
            popup.appendChild(link);
            if (form) {
                const routeButton = document.createElement("button");
                routeButton.type = "button";
                routeButton.textContent = "Plan Route";
                routeButton.className = "mini-button popup-route-button";
                routeButton.addEventListener("click", () => {
                    form.elements.destination_slug.value = marker.detail_url.split("/").pop();
                    form.dispatchEvent(new Event("change"));
                    form.scrollIntoView({ block: "nearest" });
                    document.getElementById("route-use-location").focus();
                    map.closePopup();
                });
                popup.appendChild(routeButton);
            }
            // Coordinates have passed the numeric/range checks above. Use fixed
            // Google endpoints and encode parameters; no database text enters URLs.
            const coordinates = `${marker.latitude},${marker.longitude}`;
            const more = document.createElement("div");
            more.className = "popup-more";
            for (const [label, path, parameters] of [
                ["Google Maps", "search/", { api: "1", query: coordinates }],
                ["Street View", "@", { api: "1", map_action: "pano", viewpoint: coordinates }],
                ["Satellite", "@", { api: "1", map_action: "map", center: coordinates,
                    zoom: "18", basemap: "satellite" }],
            ]) {
                const external = document.createElement("a");
                external.href = `https://www.google.com/maps/${path}?${new URLSearchParams(parameters)}`;
                external.textContent = label;
                external.target = "_blank";
                external.rel = "noopener noreferrer";
                more.appendChild(external);
            }
            popup.appendChild(more);
            const notice = document.createElement("p");
            notice.textContent = "Google Maps links open in a new tab. Street View coverage is not guaranteed.";
            popup.appendChild(notice);
            L.marker([marker.latitude, marker.longitude], {
                title: marker.name, alt: marker.name, keyboard: true,
            }).addTo(map).bindPopup(popup, { maxWidth: 280, minWidth: 210 });
        }
        const positions = [...new Map(markers.map((marker) => [
            `${marker.latitude},${marker.longitude}`, [marker.latitude, marker.longitude],
        ])).values()];
        if (positions.length === 1) map.setView(positions[0], 14);
        else map.fitBounds(positions, { padding: [24, 24], maxZoom: 16 });
        if (form) setupRouting(form, map, L, markers);
    } catch (_) {
        if (map) {
            try { map.remove(); } catch (_) { /* Keep the textual fallback available. */ }
        }
        container.hidden = true;
        if (failure) failure.hidden = false;
    }
    function setupRouting(form, map, L, markers) {
        const status = document.getElementById("route-status");
        const submit = form.querySelector('button[type="submit"]');
        let routeLayer, startMarker, controller, choosingStart = false, revision = 0;
        let locating = false;
        const latitude = form.elements.start_latitude;
        const longitude = form.elements.start_longitude;
        const chosen = new URLSearchParams(window.location.search).get("destination");
        if ([...form.elements.destination_slug.options].some(option => option.value === chosen)) {
            form.elements.destination_slug.value = chosen;
        }
        form.hidden = false;
        const say = text => { status.textContent = text; };
        const summary = document.getElementById("route-summary");
        const summaryBody = document.getElementById("route-summary-body");
        function showSummary(title, entries, message) {
            if (!summary || !summaryBody) return;
            document.getElementById('route-result-title').textContent = title;
            summaryBody.textContent = '';
            if(message){const note=document.createElement('p');note.textContent=message;summaryBody.appendChild(note);}
            for(const [label,value] of entries){const row=document.createElement('div');row.className='route-summary-row';const name=document.createElement('span');name.textContent=label;const detail=document.createElement('strong');detail.textContent=value;row.appendChild(name);row.appendChild(detail);summaryBody.appendChild(row);}
            const destination=markers.find(m=>m.detail_url.split('/').pop()===form.elements.destination_slug.value);
            if(destination){const external=document.createElement('a');external.className='mini-button';external.textContent='Open in Google Maps';external.target='_blank';external.rel='noopener noreferrer';external.href='https://www.google.com/maps/search/?'+new URLSearchParams({api:'1',query:destination.latitude+','+destination.longitude});summaryBody.appendChild(external);}
            summary.hidden=false;
        }
        function clearRoute() {
            if(summary)summary.hidden=true;
            revision += 1;
            if (controller) controller.abort();
            if (routeLayer) { map.removeLayer(routeLayer); routeLayer = null; }
            if (startMarker) { map.removeLayer(startMarker); startMarker = null; }
            submit.disabled = false;
            say("");
        }
        function setStart(lat, lon) {
            clearRoute();
            latitude.value = String(lat);
            longitude.value = String(lon);
            startMarker = L.marker([lat, lon], { title: "Starting point" }).addTo(map);
            say("Starting point selected. Select Plan Route when you are ready.");
        }
        form.addEventListener("input", clearRoute);
        form.addEventListener("change", clearRoute);
        document.getElementById("route-pick-start").addEventListener("click", () => {
            clearRoute();
            choosingStart = true;
            say("Select a starting point on the map. You can also enter coordinates manually.");
        });
        map.on("click", event => {
            if (!choosingStart) return;
            choosingStart = false;
            locating = false;
            setStart(event.latlng.lat, event.latlng.lng);
        });
        document.getElementById("route-use-location").addEventListener("click", () => {
            if (document.body?.dataset?.locationEnabled === 'false') {
                say("Location requests are turned off in Settings. Use the map or enter coordinates instead.");
                return;
            }
            clearRoute();
            choosingStart = false;
            if (!navigator.geolocation) {
                say("Device location is unavailable. Enter coordinates or select a point on the map.");
                return;
            }
            locating = true;
            const locationRevision = revision;
            say("Waiting for device location permission…");
            navigator.geolocation.getCurrentPosition(position => {
                if (!locating || revision !== locationRevision) return;
                locating = false;
                setStart(position.coords.latitude, position.coords.longitude);
            }, () => {
                if (!locating || revision !== locationRevision) return;
                locating = false;
                say("Device location could not be obtained. Enter coordinates or select a point on the map.");
            }, { timeout: 10000, maximumAge: 0, enableHighAccuracy: false });
        });
        form.addEventListener("submit", async event => {
            event.preventDefault();
            if(!latitude.value.trim()||!longitude.value.trim()) { say('Choose your Starting Point using your location, the map, or manual coordinates.');document.getElementById('route-use-location').focus();return; }
            if (!form.reportValidity()) {const advanced=form.querySelector('.manual-coordinates');if(advanced)advanced.open=true;return;}
            clearRoute();
            choosingStart = false;
            locating = false;
            const requestRevision = revision;
            const mode = form.elements.mode.value;
            const start = [Number(latitude.value), Number(longitude.value)];
            if (!Number.isFinite(start[0]) || Math.abs(start[0]) > 90 ||
                !Number.isFinite(start[1]) || Math.abs(start[1]) > 180) {
                say("Enter valid starting coordinates.");
                return;
            }
            controller = new AbortController();
            const requestController = controller;
            const timer = window.setTimeout(() => requestController.abort(), 20000);
            submit.disabled = true;
            say("Requesting a route…");
            try {
                const response = await fetch(form.action, {
                    method: "POST", credentials: "same-origin", signal: requestController.signal,
                    headers: { "Content-Type": "application/json", "Accept": "application/json" },
                    body: JSON.stringify({ destination_slug: form.elements.destination_slug.value,
                        start_latitude: start[0], start_longitude: start[1], mode }),
                });
                const data = await response.json();
                if (revision !== requestRevision) return;
                if (!response.ok) {
                    const errors = {
                        invalid_coordinates: "Enter valid starting coordinates.",
                        missing_coordinates: "This destination has no verified coordinates yet.",
                        unsupported_mode: "This transportation mode is unavailable for routing.",
                        destination_unavailable: "This destination is no longer available.",
                        no_route: "We couldn't calculate a route between these points. Try a different starting point or open the destination in Google Maps.",
                        provider_timeout: "The route request timed out. Please try again.",
                        rate_limited: "Please wait a moment before requesting another route.",
                    };
                    const message=errors[data.error] || "We couldn't calculate this route right now. Try again or open the destination in Google Maps.";
                    say(message);showSummary('Route unavailable',[],message);
                    return;
                }
                if (!data.geometry || data.geometry.type !== "LineString" ||
                    !Array.isArray(data.geometry.coordinates) || data.geometry.coordinates.length < 2 ||
                    !Number.isFinite(data.distance_m) || data.distance_m < 0 ||
                    !Number.isFinite(data.duration_s) || data.duration_s < 0 || data.mode !== mode) {
                    throw new Error("Invalid route response");
                }
                routeLayer = L.geoJSON({ type: "Feature", properties: {}, geometry: data.geometry },
                    { style: { color: "#96281b", weight: 5 } }).addTo(map);
                startMarker = L.marker(start, { title: "Starting point" }).addTo(map);
                map.fitBounds(routeLayer.getBounds().extend(start), { padding: [24, 24] });
                const destination=markers.find(m=>m.detail_url.split('/').pop()===form.elements.destination_slug.value);
                showSummary('Route Summary', [['Destination',destination.name],['Mode',({driving:'Driving',walking:'Walking',cycling:'Cycling'})[mode]],['Distance',(data.distance_m/1000).toFixed(2)+' km'],['Estimated travel time',Math.ceil(data.duration_s/60)+' minutes']]);
                say(`Estimated distance: ${(data.distance_m / 1000).toFixed(2)} km. ` +
                    `Estimated travel duration: ${Math.ceil(data.duration_s / 60)} minutes. ` +
                    "Estimates exclude live traffic and stops.");
            } catch (_) {
                if (revision !== requestRevision) return;
                if (routeLayer) { map.removeLayer(routeLayer); routeLayer = null; }
                const message="We couldn't load this route. Try a different starting point or open the destination in Google Maps.";
                say(message);showSummary('Route unavailable',[],message);
            } finally {
                window.clearTimeout(timer);
                if (revision === requestRevision) submit.disabled = false;
            }
        });
    }
})();
